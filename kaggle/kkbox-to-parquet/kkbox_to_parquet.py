# Runs on Kaggle. Unpacks the KKBox competition files and writes each one as Parquet
# to /kaggle/working/kkbox/<name>/, which becomes this notebook's output (input to later notebooks).
import glob, hashlib, json, os, shutil, subprocess, sys

subprocess.run([sys.executable, "-m", "pip", "install", "-q", "pyspark==4.0.1", "py7zr"], check=True)
if not shutil.which("java"):
    subprocess.run("apt-get update -qq && apt-get install -y -qq openjdk-17-jre-headless", shell=True, check=True)

import py7zr
from pyspark.sql import SparkSession, functions as F

SRC = os.path.dirname(glob.glob("/kaggle/input/**/transactions.csv*", recursive=True)[0])
TMP, OUT = "/tmp/kkbox", "/kaggle/working/kkbox"
os.makedirs(TMP, exist_ok=True)
print("input files:", sorted(os.listdir(SRC)))

D = "date"  # yyyymmdd ints → real dates
SCHEMAS = {
    "train_v2": ("msno string, is_churn int", []),
    "transactions": ("msno string, payment_method_id int, payment_plan_days int, plan_list_price int, "
                     "actual_amount_paid int, is_auto_renew int, transaction_date string, "
                     "membership_expire_date string, is_cancel int", ["transaction_date", "membership_expire_date"]),
    "members_v3": ("msno string, city int, bd int, gender string, registered_via int, "
                   "registration_init_time string", ["registration_init_time"]),
    "user_logs_v2": ("msno string, date string, num_25 int, num_50 int, num_75 int, num_985 int, "
                     "num_100 int, num_unq int, total_secs double", ["date"]),
}
SCHEMAS["transactions_v2"] = SCHEMAS["transactions"]


def find_csv(name):
    """Return a path to <name>.csv, unpacking <name>.csv.7z (or .zip) if that's how Kaggle ships it."""
    for p in glob.glob(f"{SRC}/**/{name}.csv*", recursive=True):
        if p.endswith(".csv"):
            return p
        if p.endswith(".7z"):
            with py7zr.SevenZipFile(p) as z:
                z.extractall(TMP)
        else:
            shutil.unpack_archive(p, TMP)
        hits = glob.glob(f"{TMP}/**/{name}.csv", recursive=True)
        if hits:
            return hits[0]
    raise FileNotFoundError(name)


def sha256(path, max_lines=None):
    h, n = hashlib.sha256(), 0
    with open(path, "rb") as f:
        for line in f:
            if max_lines is not None and n >= max_lines:
                break
            h.update(line.rstrip(b"\r\n") + b"\n")  # line-ending neutral, comparable with the Excel-saved mirror
            n += 1
    return h.hexdigest()


spark = (SparkSession.builder.master("local[*]").appName("kkbox-to-parquet")
         .config("spark.sql.session.timeZone", "UTC")
         .config("spark.driver.memory", "16g").getOrCreate())
spark.sparkContext.setLogLevel("ERROR")

manifest = {}
for name, (schema, date_cols) in SCHEMAS.items():
    csv = find_csv(name)
    df = spark.read.csv(csv, header=True, schema=schema)
    for c in date_cols:
        df = df.withColumn(c, F.to_date(c, "yyyyMMdd"))
    df.write.mode("overwrite").parquet(f"{OUT}/{name}")
    back = spark.read.parquet(f"{OUT}/{name}").count()
    lines = sum(1 for _ in open(csv, "rb")) - 1
    assert back == lines, (name, back, lines)  # every CSV row made it into Parquet
    manifest[name] = {"rows": back, "csv_sha256": sha256(csv), "csv_bytes": os.path.getsize(csv)}
    if name == "transactions_v2":  # same hash the mirror gives over its rows, to test the overlap
        manifest[name]["sha256_first_1048576_lines"] = sha256(csv, 1048576)
    print(name, manifest[name], flush=True)
    os.remove(csv)  # keep /tmp small

json.dump(manifest, open("/kaggle/working/manifest.json", "w"), indent=2)
print(json.dumps(manifest, indent=2))
