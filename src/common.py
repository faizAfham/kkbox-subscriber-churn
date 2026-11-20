import os, sys
from pathlib import Path

os.environ.setdefault("PYSPARK_PYTHON", sys.executable)  # workers must use the same Python as the driver

ROOT = Path(__file__).resolve().parents[1]
LANDING = ROOT / "data/landing"
LAKE = ROOT / "data/lake"  # Delta tables: bronze/, silver/, gold/, dq/
CHANNELS = ["direct", "apple", "roku", "amazon"]


def table(layer, name):
    return str(LAKE / layer / name)


def spark(app="subscriber-movements"):
    from delta import configure_spark_with_delta_pip
    from pyspark.sql import SparkSession
    b = (SparkSession.builder.master("local[4]").appName(app)
         .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
         .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog")
         .config("spark.sql.session.timeZone", "UTC")
         .config("spark.sql.shuffle.partitions", "8")  # ponytail: laptop-sized; raise on a cluster
         .config("spark.ui.showConsoleProgress", "false")
         .config("spark.driver.memory", "3g"))
    s = configure_spark_with_delta_pip(b).getOrCreate()
    s.sparkContext.setLogLevel("ERROR")
    return s


def exists(path):
    from delta.tables import DeltaTable
    from pyspark.sql import SparkSession
    return DeltaTable.isDeltaTable(SparkSession.getActiveSession(), path)
