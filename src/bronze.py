"""Bronze: land one day of raw webhooks per channel into Delta, untouched.

Raw JSON is kept as a string (schema-on-read). If a partner changes its payload,
bronze still loads and silver is where we notice. Rerunning a day overwrites only
that day (replaceWhere), so the task is idempotent and safe for Airflow retries.

usage: python src/bronze.py 2017-03-05
"""
import sys
from pyspark.sql import functions as F
from common import CHANNELS, LANDING, spark, table


def run(ds):
    s = spark("bronze")
    frames = []
    for ch in CHANNELS:
        p = LANDING / ch / f"dt={ds}"
        if p.exists():
            frames.append(s.read.text(str(p)).select(
                F.col("value").alias("raw_json"), F.lit(ch).alias("channel"),
                F.to_date(F.lit(ds)).alias("ingest_date"), F.input_file_name().alias("source_file"),
                F.current_timestamp().alias("ingested_at")))
    if not frames:
        print(f"bronze {ds}: no files landed")
        return 0
    df = frames[0]
    for f in frames[1:]:
        df = df.unionByName(f)
    (df.write.format("delta").mode("overwrite").option("replaceWhere", f"ingest_date = '{ds}'")
     .partitionBy("ingest_date").save(table("bronze", "webhook_events")))
    n = df.count()
    print(f"bronze {ds}: {n} rows")
    return n


if __name__ == "__main__":
    run(sys.argv[1])
