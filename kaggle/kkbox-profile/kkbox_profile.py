# Runs on Kaggle, on the Parquet output of kkbox-to-parquet. Profiling only: counts, ranges, nulls, joins.
# Deliberately computes NO churn or cancel rates by price, so the decision rule is written before any result.
import glob, json, shutil, subprocess, sys

subprocess.run([sys.executable, "-m", "pip", "install", "-q", "pyspark==4.0.1"], check=True)
if not shutil.which("java"):
    subprocess.run("apt-get update -qq && apt-get install -y -qq openjdk-17-jre-headless", shell=True, check=True)

from pyspark.sql import SparkSession, functions as F

IN = glob.glob("/kaggle/input/**/kkbox", recursive=True)[0]
spark = (SparkSession.builder.master("local[*]").appName("kkbox-profile")
         .config("spark.sql.session.timeZone", "UTC")
         .config("spark.driver.memory", "16g").getOrCreate())
spark.sparkContext.setLogLevel("ERROR")
t = {n: spark.read.parquet(f"{IN}/{n}").cache()
     for n in ["train_v2", "transactions", "transactions_v2", "members_v3", "user_logs_v2"]}

out, md = {"tables": {}}, ["# KKBox full dataset: profile", ""]

# 1. Per table: rows, users, nulls, date range
md += ["| table | rows | distinct users | date range | columns with nulls |", "|---|---|---|---|---|"]
for n, df in t.items():
    dates = [c for c, ty in df.dtypes if ty == "date"]
    agg = [F.count("*").alias("rows"), F.countDistinct("msno").alias("users")]
    agg += [F.sum(F.col(c).isNull().cast("int")).alias(f"null_{c}") for c in df.columns]
    agg += [F.min(c).alias(f"min_{c}") for c in dates] + [F.max(c).alias(f"max_{c}") for c in dates]
    r = df.agg(*agg).first().asDict()
    out["tables"][n] = {k: str(v) if hasattr(v, "isoformat") else v for k, v in r.items()}
    nulls = ", ".join(f"{c} {r[f'null_{c}']:,}" for c in df.columns if r[f"null_{c}"]) or "none"
    rng = "; ".join(f"{c} {r[f'min_{c}']} → {r[f'max_{c}']}" for c in dates) or "-"
    md.append(f"| {n} | {r['rows']:,} | {r['users']:,} | {rng} | {nulls} |")

# 2. How the files join, starting from the labelled March cohort
lab = t["train_v2"].select("msno")
def users(n): return t[n].select("msno").distinct()
joins = {
    "labelled users (train_v2)": lab.count(),
    "… with a March transaction": lab.join(users("transactions_v2"), "msno").count(),
    "… with any pre-March transaction": lab.join(users("transactions"), "msno").count(),
    "… with a member profile": lab.join(users("members_v3"), "msno").count(),
    "… with March listening logs": lab.join(users("user_logs_v2"), "msno").count(),
}
all4 = lab
for n in ["transactions_v2", "transactions", "members_v3", "user_logs_v2"]:
    all4 = all4.join(users(n), "msno")
joins["… in all four files"] = all4.count()
out["joins"] = joins
md += ["", "## Joins from the labelled cohort", "", "| step | users |", "|---|---|"]
md += [f"| {k} | {v:,} |" for k, v in joins.items()]

# 3. Data-quality flags worth a line in the memo (counts only)
m, tx = t["members_v3"], t["transactions"].unionByName(t["transactions_v2"])
dq = {
    "members: age (bd) <= 0 or > 100": m.filter((F.col("bd") <= 0) | (F.col("bd") > 100)).count(),
    "members: gender missing": m.filter(F.col("gender").isNull()).count(),
    "transactions: exact duplicate rows": tx.count() - tx.distinct().count(),
    "transactions: list price 0": tx.filter(F.col("plan_list_price") == 0).count(),
    "transactions: paid > list price": tx.filter(F.col("actual_amount_paid") > F.col("plan_list_price")).count(),
    "transactions: expire date before transaction date": tx.filter(
        F.col("membership_expire_date") < F.col("transaction_date")).count(),
    "user_logs_v2: total_secs < 0": t["user_logs_v2"].filter(F.col("total_secs") < 0).count(),
}
out["dq"] = dq
md += ["", "## Data-quality flags", "", "| check | rows |", "|---|---|"] + [f"| {k} | {v:,} |" for k, v in dq.items()]

# 4. Shape of the categorical fields the pricing analysis will use (distribution, not outcomes)
shape = {
    "plan_days (top 10)": t["transactions_v2"].groupBy("payment_plan_days").count().orderBy(F.desc("count")).limit(10),
    "list_price (top 10)": t["transactions_v2"].groupBy("plan_list_price").count().orderBy(F.desc("count")).limit(10),
    "payment_method (top 10)": t["transactions_v2"].groupBy("payment_method_id").count().orderBy(F.desc("count")).limit(10),
}
md += ["", "## March transactions: field distributions (counts only)"]
for k, df in shape.items():
    rows = [r.asDict() for r in df.collect()]
    out[k] = rows
    col = df.columns[0]
    md += ["", f"**{k}**", "", f"| {col} | rows |", "|---|---|"] + [f"| {r[col]} | {r['count']:,} |" for r in rows]

json.dump(out, open("/kaggle/working/profile.json", "w"), indent=2, default=str)
open("/kaggle/working/profile.md", "w").write("\n".join(md) + "\n")
print("\n".join(md))
