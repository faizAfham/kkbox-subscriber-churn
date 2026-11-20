"""Daily subscriber-movements pipeline.

bronze -> silver -> dq_silver -> gold -> dq_gold -> (5th of month) reconcile last month

- One run per landing day ({{ ds }}); catchup=True replays the whole history in order.
- max_active_runs=1 because silver MERGEs into one Delta table (concurrent writers would conflict).
- A failed error-level DQ check fails its task, so gold is never rebuilt from bad silver.
- Spark jobs run as plain Python scripts from the project venv. Airflow sits in its own
  venv and only orchestrates; it never imports Spark.
"""
import os
from datetime import datetime, timedelta
from pathlib import Path

from airflow.providers.standard.operators.bash import BashOperator
from airflow.providers.standard.operators.python import ShortCircuitOperator
from airflow.sdk import DAG

ROOT = Path(__file__).resolve().parents[1]
PY = f"cd {ROOT / 'src'} && {ROOT / '.venv/bin/python'}"
ENV = {"JAVA_HOME": os.environ.get("JAVA_HOME", "/Library/Java/JavaVirtualMachines/jdk-22.jdk/Contents/Home")}

with DAG(
    dag_id="subscriber_movements",
    start_date=datetime(2017, 2, 28),
    end_date=datetime(2017, 4, 5),
    schedule="@daily",
    catchup=True,
    max_active_runs=1,
    default_args={"retries": 2, "retry_delay": timedelta(minutes=1)},
    tags=["commerce", "delta"],
) as dag:
    spark_task = lambda tid, cmd: BashOperator(task_id=tid, bash_command=f"{PY} {cmd}", env=ENV, append_env=True)

    bronze = spark_task("bronze", "bronze.py {{ ds }}")
    silver = spark_task("silver", "silver.py {{ ds }}")
    dq_silver = spark_task("dq_silver", "dq.py silver {{ ds }}")
    gold = spark_task("gold", "gold.py {{ ds }}")
    dq_gold = spark_task("dq_gold", "dq.py gold {{ ds }}")
    # Partner payout files for month M arrive a few days after it closes, so reconcile on the 5th.
    is_recon_day = ShortCircuitOperator(task_id="is_recon_day",
                                        python_callable=lambda ds: ds.endswith("-05"), op_kwargs={"ds": "{{ ds }}"})
    reconcile = spark_task("reconcile",
                           "reconcile.py {{ macros.ds_format(macros.ds_add(ds, -5), '%Y-%m-%d', '%Y-%m') }}")

    bronze >> silver >> dq_silver >> gold >> dq_gold >> is_recon_day >> reconcile
