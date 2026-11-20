# Runs on Kaggle on kkbox-to-parquet's output. Phase 1: billing ledger (silver) + one row per labelled user (gold mart).
# Prints counts and DQ checks only: no churn/cancel rate by price (that is Phase 2, against analysis/decision_rule.md).
import glob, json, shutil, subprocess, sys

subprocess.run([sys.executable, "-m", "pip", "install", "-q", "pyspark==4.0.1"], check=True)
if not shutil.which("java"):
    subprocess.run("apt-get update -qq && apt-get install -y -qq openjdk-17-jre-headless", shell=True, check=True)

from pyspark.sql import SparkSession, Window, functions as F

IN = glob.glob("/kaggle/input/**/kkbox", recursive=True)[0]
OUT = "/kaggle/working"
spark = (SparkSession.builder.master("local[*]").appName("kkbox-pricing-mart")
         .config("spark.sql.session.timeZone", "UTC")
         .config("spark.driver.memory", "16g").getOrCreate())
spark.sparkContext.setLogLevel("ERROR")
rd = lambda n: spark.read.parquet(f"{IN}/{n}")
CUTOFF, MARCH_END = "2017-02-28", "2017-03-31"
TIERS = [99, 100, 129, 149, 180]

# ---- silver.billing_ledger: both transaction files, exact duplicates dropped, bad rows flagged (not deleted)
tx = rd("transactions").unionByName(rd("transactions_v2"))
ledger = (tx.dropDuplicates()
          .withColumn("is_free", F.col("plan_list_price") == 0)
          .withColumn("is_bad_dates", F.col("membership_expire_date") < F.col("transaction_date"))
          .withColumn("is_discounted", F.col("actual_amount_paid") < F.col("plan_list_price")))
ledger.write.mode("overwrite").parquet(f"{OUT}/silver/billing_ledger")
ledger = spark.read.parquet(f"{OUT}/silver/billing_ledger")

# ---- per user: the expiring subscription = last valid transaction on or before the cutoff
valid_pre = ledger.filter((F.col("transaction_date") <= CUTOFF) & ~F.col("is_bad_dates"))
w = Window.partitionBy("msno").orderBy(F.desc("transaction_date"), F.desc("membership_expire_date"))
ranked = valid_pre.withColumn("rk", F.row_number().over(w))
cur = ranked.filter("rk = 1").select(
    "msno", F.col("plan_list_price").alias("price"), F.col("payment_plan_days").alias("plan_days"),
    F.col("payment_method_id").alias("pm"), F.col("is_auto_renew").alias("auto_renew"),
    F.col("actual_amount_paid").alias("paid"), F.col("transaction_date").alias("cur_tx_date"),
    F.col("membership_expire_date").alias("cur_expire"), "is_free", "is_discounted")
# previous 30-day plan price, for the "price went up" check
prev = (ranked.filter((F.col("rk") > 1) & (F.col("payment_plan_days") == 30))
        .withColumn("rk2", F.row_number().over(Window.partitionBy("msno").orderBy("rk")))
        .filter("rk2 = 1").select("msno", F.col("plan_list_price").alias("prev_price")))
first = ledger.groupBy("msno").agg(F.min("transaction_date").alias("first_tx_date"))

# March outcome-side fields (guardrails only)
mar = ledger.filter(F.col("transaction_date").between("2017-03-01", MARCH_END))
mar_u = mar.groupBy("msno").agg(
    F.max("is_cancel").alias("cancelled_in_march"),
    F.min(F.when(F.col("is_cancel") == 0, F.col("plan_list_price"))).alias("march_renew_price"))

logs = rd("user_logs_v2").groupBy("msno").agg(
    F.countDistinct("date").alias("listen_days_march"), F.sum("total_secs").alias("listen_secs_march"),
    F.sum("num_unq").alias("unique_songs_march"))
mem = rd("members_v3").select(
    "msno", "city", "registered_via", "registration_init_time",
    F.when(F.col("bd").between(1, 100), F.col("bd")).alias("age"),  # 0/negative/>100 = unknown
    "gender")

mart = (rd("train_v2").join(cur, "msno", "left").join(prev, "msno", "left").join(first, "msno", "left")
        .join(mar_u, "msno", "left").join(logs, "msno", "left").join(mem, "msno", "left")
        .withColumn("tenure_days", F.datediff("cur_tx_date", "first_tx_date"))
        .withColumn("tenure_band", F.when(F.col("tenure_days") < 365, "<1y")
                    .when(F.col("tenure_days") < 730, "1-2y").otherwise(">2y"))
        .withColumn("price_rose", F.col("price") > F.col("prev_price"))
        .withColumn("downgraded", F.col("march_renew_price") < F.col("price"))
        .withColumn("expires_in_march", F.col("cur_expire").between("2017-03-01", MARCH_END)))

# funnel flags: every step is a column so the funnel is reproducible from the mart alone
steps = [
    ("has an expiring subscription (valid tx on/before Feb 28)", F.col("price").isNotNull()),
    ("30-day plan", F.col("plan_days") == 30),
    ("auto-renew on", F.col("auto_renew") == 1),
    ("not free (list price > 0)", ~F.col("is_free")),
    ("price is one of 99/100/129/149/180", F.col("price").isin(TIERS)),
]
cond = F.lit(True)
for i, (_, c) in enumerate(steps, 1):
    cond = cond & F.coalesce(c, F.lit(False))
    mart = mart.withColumn(f"step{i}", cond)
mart = mart.withColumn("in_cohort", F.col(f"step{len(steps)}") & (F.col("pm") == 41))
mart.write.mode("overwrite").parquet(f"{OUT}/gold/mart_pricing_user")
mart = spark.read.parquet(f"{OUT}/gold/mart_pricing_user").cache()

# ---- funnel (counts only)
n = mart.count()
funnel = [("labelled users (train_v2)", n)]
funnel += [(name, mart.filter(f"step{i}").count()) for i, (name, _) in enumerate(steps, 1)]
funnel.append(("payment method 41 (decision-rule cohort)", mart.filter("in_cohort").count()))
info = {  # context counts for the memo, still no outcomes
    "expiring sub actually expires in March (of step 5)": mart.filter("step5 and expires_in_march").count(),
    "tier users by price (step 5)": {r["price"]: r["count"] for r in mart.filter("step5").groupBy("price").count().collect()},
    "cohort by price (pm41)": {r["price"]: r["count"] for r in mart.filter("in_cohort").groupBy("price").count().collect()},
    "cohort by tenure band": {r["tenure_band"]: r["count"] for r in mart.filter("in_cohort").groupBy("tenure_band").count().collect()},
    "cohort with a previous 30-day price": mart.filter("in_cohort and prev_price is not null").count(),
    "cohort whose price rose": mart.filter("in_cohort and price_rose").count(),
    "cohort with valid age": mart.filter("in_cohort and age is not null").count(),
    "cohort with March listening logs": mart.filter("in_cohort and listen_days_march is not null").count(),
}

# ---- DQ checks (error = fail the notebook)
led_n, tx_n = ledger.count(), tx.count()
dq = {
    "mart: one row per user": mart.select("msno").distinct().count() == n,
    "mart: row count = train_v2": n == rd("train_v2").count(),
    "ledger: no exact duplicates left": led_n == ledger.distinct().count(),
    "ledger: rows = input - exact duplicates": led_n == tx.distinct().count(),
    "cohort: every row has a tier": mart.filter("in_cohort and not price in (99,100,129,149,180)").count() == 0,
    "cohort: churn label never null": mart.filter("in_cohort and is_churn is null").count() == 0,
    "funnel: never increases": all(a[1] >= b[1] for a, b in zip(funnel, funnel[1:])),
}
md = ["# Pricing mart: funnel and DQ", "", f"Ledger: {tx_n:,} input rows → {led_n:,} after dropping exact duplicates.", "",
      "| step | users left | dropped |", "|---|---|---|"]
md += [f"| {s} | {c:,} | {'' if i == 0 else f'{funnel[i-1][1] - c:,}'} |" for i, (s, c) in enumerate(funnel)]
md += ["", "## Context counts (no outcomes)", ""] + [f"- {k}: {v}" for k, v in info.items()]
md += ["", "## DQ checks", ""] + [f"- {'PASS' if ok else 'FAIL'}: {k}" for k, ok in dq.items()]
open(f"{OUT}/funnel.md", "w").write("\n".join(md) + "\n")
json.dump({"funnel": funnel, "info": info, "dq": dq}, open(f"{OUT}/funnel.json", "w"), indent=2, default=str)
print("\n".join(md))
assert all(dq.values()), "DQ failed"
