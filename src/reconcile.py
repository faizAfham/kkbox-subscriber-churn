"""Partner payout reconciliation: what Apple/Roku/Amazon/our processor say they paid us
vs what our own event ledger says we earned.

Each partner sends a monthly payout CSV. We full-outer-join it to silver paid events on
(channel, transaction id) and sort every row into one bucket:
  matched           both sides agree on gross
  amount_mismatch   both sides have it, gross differs (FX, rounding, proration)
  missing_in_report we billed it, partner did not pay it  -> chase the partner
  unknown_to_us     partner paid it, we have no event      -> lost webhook? investigate
Writes gold/recon_payout_detail and gold/recon_payout_summary.

usage: python src/reconcile.py 2017-03
"""
import sys
from pyspark.sql import functions as F
from common import CHANNELS, LANDING, spark, table


def run(month):
    s = spark("reconcile")
    rep = None
    for ch in CHANNELS:
        p = LANDING / "payout_reports" / f"{ch}_{month}.csv"
        if p.exists():
            df = s.read.option("header", True).csv(str(p)).withColumn("channel", F.lit(ch))
            rep = df if rep is None else rep.unionByName(df)
    if rep is None:
        print(f"reconcile {month}: no payout reports landed, nothing to do")
        return
    rep = rep.select("channel", F.col("partner_txn_id").alias("event_id"),
                     F.col("gross_twd").cast("decimal(12,2)").alias("partner_gross"),
                     F.col("net_twd").cast("decimal(12,2)").alias("partner_net"))
    ours = (s.read.format("delta").load(table("silver", "subscription_events"))
            .where((F.date_format("event_date", "yyyy-MM") == month) & (F.col("amount_twd") != 0) &
                   (F.col("event_type") != "CANCEL"))
            .select("channel", "event_id", "event_type", F.col("amount_twd").alias("our_gross")))
    detail = (ours.join(rep, ["channel", "event_id"], "full_outer")
              .withColumn("status", F.when(F.col("partner_gross").isNull(), "missing_in_report")
                          .when(F.col("our_gross").isNull(), "unknown_to_us")
                          .when(F.col("our_gross") != F.col("partner_gross"), "amount_mismatch")
                          .otherwise("matched"))
              .withColumn("gross_diff", F.coalesce("partner_gross", F.lit(0)) - F.coalesce("our_gross", F.lit(0)))
              .withColumn("month", F.lit(month)))
    detail.write.format("delta").mode("overwrite").option("overwriteSchema", "true").save(table("gold", "recon_payout_detail"))
    summary = (detail.groupBy("month", "channel").agg(
        F.count("*").alias("rows"),
        *[F.sum((F.col("status") == k).cast("int")).alias(k) for k in
          ["matched", "amount_mismatch", "missing_in_report", "unknown_to_us"]],
        F.sum("our_gross").alias("our_gross_twd"), F.sum("partner_gross").alias("partner_gross_twd"),
        F.sum("partner_net").alias("partner_net_twd"), F.sum("gross_diff").alias("gross_variance_twd"))
        .withColumn("match_rate", F.round(F.col("matched") / F.col("rows"), 4)).orderBy("channel"))
    summary.write.format("delta").mode("overwrite").option("overwriteSchema", "true").save(table("gold", "recon_payout_summary"))
    summary.show(truncate=False)


if __name__ == "__main__":
    run(sys.argv[1])
