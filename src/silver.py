"""Silver: four partner formats -> one clean subscription_events table.

Per channel we parse the payload and convert to one schema:
  event_id, channel, subscription_id, event_type (NEW/RENEW/CANCEL/REFUND),
  event_ts (UTC), amount_twd (refund negative), plan_days, expires_date, auto_renew
Then:
  - bad rows (no amount on a money event, unparseable) -> silver/quarantine with a reason
  - duplicates inside the day are dropped; duplicates across days are blocked by a MERGE
    on (channel, event_id), so a retried webhook three days later is still counted once
  - late events are kept (flagged is_late) and land in the right event_date partition

usage: python src/silver.py 2017-03-05
"""
import sys
from delta.tables import DeltaTable
from pyspark.sql import functions as F, types as T
from common import exists, spark, table

J = F.get_json_object  # ponytail: path lookups are enough here; from_json + schemas if payloads grow


def parse(df):
    c, raw = F.col("channel"), F.col("raw_json")
    ms_ts = lambda path: F.timestamp_millis(J(raw, path).cast("long"))
    kind = (F.when(c == "apple", F.element_at(F.create_map(*[F.lit(x) for x in [
                "SUBSCRIBED", "NEW", "DID_RENEW", "RENEW", "DID_CHANGE_RENEWAL_STATUS", "CANCEL", "REFUND", "REFUND"]]),
                J(raw, "$.notificationType")))
            .when(c == "direct", F.when(J(raw, "$.type") == "charge.refunded", "REFUND")
                  .when(J(raw, "$.type") == "customer.subscription.updated", "CANCEL")
                  .when(J(raw, "$.data.object.billing_reason") == "subscription_create", "NEW")
                  .when(J(raw, "$.data.object.billing_reason") == "subscription_cycle", "RENEW"))
            .when(c == "roku", F.element_at(F.create_map(*[F.lit(x) for x in [
                "Purchase", "NEW", "Renewal", "RENEW", "Cancellation", "CANCEL", "Refund", "REFUND"]]),
                J(raw, "$.eventType")))
            .otherwise(F.element_at(F.create_map(*[F.lit(x) for x in [
                "PURCHASE", "NEW", "RENEWAL", "RENEW", "CANCEL", "CANCEL", "REFUND", "REFUND"]]),
                J(raw, "$.eventType"))))
    return df.select(
        F.when(c == "apple", J(raw, "$.data.transactionId"))
         .when(c == "direct", F.regexp_replace(J(raw, "$.id"), "^evt_", ""))
         .when(c == "roku", J(raw, "$.transactionId"))
         .otherwise(J(raw, "$.receiptId")).alias("event_id"),
        c,
        F.when(c == "apple", J(raw, "$.data.originalTransactionId"))
         .when(c == "direct", F.regexp_replace(J(raw, "$.data.object.subscription"), "^sub_", ""))
         .when(c == "roku", J(raw, "$.customerId"))
         .otherwise(J(raw, "$.userId")).alias("subscription_id"),
        kind.alias("event_type"),
        F.when(c == "apple", ms_ts("$.signedDate"))
         .when(c == "direct", F.timestamp_seconds(J(raw, "$.created").cast("long")))
         .when(c == "roku", F.to_timestamp(J(raw, "$.eventDate")))  # ISO with +08:00 offset
         .otherwise(F.to_utc_timestamp(F.to_timestamp(J(raw, "$.purchaseDate")), "Asia/Taipei"))  # no offset sent
         .alias("event_ts"),
        (F.when(c == "apple", J(raw, "$.data.price").cast("double") / 1000)
          .when(c == "direct", J(raw, "$.data.object.amount").cast("double") / 100)
          .when(c == "roku", J(raw, "$.amount").cast("double"))
          .otherwise(J(raw, "$.priceTWD").cast("double"))).cast(T.DecimalType(12, 2)).alias("amount_raw"),
        F.regexp_extract(F.coalesce(J(raw, "$.data.productId"), J(raw, "$.data.object.plan"),
                                    J(raw, "$.productCode"), J(raw, "$.sku")), r"plus_(\d+)d", 1)
         .cast("int").alias("plan_days"),
        F.coalesce(F.to_date(ms_ts("$.data.expiresDate")),
                   F.to_date(F.timestamp_seconds(J(raw, "$.data.object.period_end").cast("long"))),
                   F.to_date(J(raw, "$.expirationDate")), F.to_date(J(raw, "$.renewalDate"))).alias("expires_date"),
        F.coalesce(J(raw, "$.data.autoRenewStatus") == "1",
                   ~J(raw, "$.data.object.cancel_at_period_end").cast("boolean"),
                   J(raw, "$.autoRenewing").cast("boolean")).alias("auto_renew"),
        "ingest_date", "raw_json")


def run(ds):
    s = spark("silver")
    bronze = s.read.format("delta").load(table("bronze", "webhook_events")).where(F.col("ingest_date") == ds)
    p = parse(bronze)
    reason = (F.when(F.col("event_id").isNull(), "missing_event_id")
              .when(F.col("event_type").isNull(), "unknown_event_type")
              .when(F.col("event_ts").isNull(), "bad_timestamp")
              .when(F.col("event_type").isin("NEW", "RENEW", "REFUND") & F.col("amount_raw").isNull(), "missing_amount"))
    p = p.withColumn("reject_reason", reason).cache()

    bad = p.where(F.col("reject_reason").isNotNull()).select("channel", "ingest_date", "reject_reason", "raw_json")
    bad.write.format("delta").mode("overwrite").option("replaceWhere", f"ingest_date = '{ds}'") \
        .partitionBy("ingest_date").save(table("silver", "quarantine"))

    good = (p.where(F.col("reject_reason").isNull())
            .withColumn("amount_twd", F.when(F.col("event_type") == "REFUND", -F.col("amount_raw"))
                        .otherwise(F.coalesce(F.col("amount_raw"), F.lit(0)).cast(T.DecimalType(12, 2))))
            .withColumn("event_date", F.to_date("event_ts"))
            .withColumn("is_late", F.datediff(F.col("ingest_date"), F.col("event_date")) > 1)
            .drop("amount_raw", "reject_reason", "raw_json")
            .dropDuplicates(["channel", "event_id"]))

    path = table("silver", "subscription_events")
    if not exists(path):
        good.write.format("delta").partitionBy("event_date").save(path)
    else:  # insert-only merge: a re-delivered webhook from an earlier day is ignored
        (DeltaTable.forPath(s, path).alias("t")
         .merge(good.alias("s"), "t.channel = s.channel AND t.event_id = s.event_id")
         .whenNotMatchedInsertAll().execute())
    total, nbad, ngood = p.count(), bad.count(), good.count()
    m = DeltaTable.forPath(s, path).history(1).collect()[0]["operationMetrics"]
    ins = int(m.get("numTargetRowsInserted", m.get("numOutputRows", ngood)))
    print(f"silver {ds}: {total} parsed, {nbad} quarantined, {total - nbad - ngood} same-day dupes, "
          f"{ngood - ins} cross-day dupes, {ins} inserted")
    return {"parsed": total, "quarantined": nbad, "inserted": ins}


if __name__ == "__main__":
    run(sys.argv[1])
