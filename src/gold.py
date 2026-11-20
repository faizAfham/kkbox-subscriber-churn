"""Gold: star schema + daily subscriber movements, rebuilt from silver.

Tables (data/lake/gold/):
  dim_date, dim_channel, dim_plan
  dim_subscription            SCD2: a new version whenever channel, plan or auto-renew changes
  fact_subscription_event     one row per billing event, net of partner commission
  fact_subscriber_daily       grain = subscription x day (active flag), the base for movements
  agg_subscriber_movements    grain = day x channel x plan: active, new, reactivated, churned, net adds, revenue

How "active" works: each event opens a segment that lasts until the next event for that
subscription. Inside a segment the subscription is active while day < expires_date
(a refund ends it on the refund day). A movement is a change in the active flag vs yesterday.

ponytail: full rebuild each run (~1M events, under a minute on a laptop). Switch to an
incremental MERGE on affected subscriptions once silver is too big to rescan.

usage: python src/gold.py 2017-03-31   (snapshot window ends on this day)
"""
import sys
from pyspark.sql import Window, functions as F
from common import spark, table

SNAPSHOT_START = "2017-03-01"
COMMISSION = {"direct": 0.03, "apple": 0.30, "roku": 0.20, "amazon": 0.30}  # must match partner contracts
PLAN_NAMES = {30: "Monthly", 31: "Monthly", 90: "Quarterly", 180: "Half-yearly", 195: "Half-yearly", 360: "Yearly",
              395: "Yearly", 410: "Yearly", 7: "Trial", 0: "Free / promo"}


def save(df, name):
    df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").save(table("gold", name))


def run(end):
    s = spark("gold")
    # cached: ev feeds the SCD2 dim, the fact and the daily snapshot; without this Spark rereads
    # and re-parses silver for each of them (gold went from >10 min to ~2 on a laptop)
    ev = s.read.format("delta").load(table("silver", "subscription_events")).where(F.col("event_date") <= end).cache()

    # --- small dimensions -------------------------------------------------------------
    save(s.sql(f"SELECT explode(sequence(DATE'2015-01-01', DATE'{end}')) AS date")
         .select(F.date_format("date", "yyyyMMdd").cast("int").alias("date_key"), "date",
                 F.year("date").alias("year"), F.month("date").alias("month"),
                 F.date_format("date", "E").alias("weekday"), F.dayofweek("date").isin(1, 7).alias("is_weekend")),
         "dim_date")
    save(s.createDataFrame([(c, "first-party" if c == "direct" else "partner", r) for c, r in COMMISSION.items()],
                           "channel string, billing_type string, commission_rate double"), "dim_channel")
    plan_map = F.create_map(*[x for k, v in PLAN_NAMES.items() for x in (F.lit(k), F.lit(v))])
    save(ev.select("plan_days").distinct()
         .withColumn("plan_name", F.coalesce(F.element_at(plan_map, F.col("plan_days")), F.lit("Other"))), "dim_plan")

    # --- SCD2 subscription dimension ----------------------------------------------------
    w = Window.partitionBy("subscription_id").orderBy("event_ts", "event_id")
    attrs = ["channel", "plan_days", "auto_renew"]
    changed = ev.where("event_type != 'REFUND'").select("subscription_id", "event_ts", "event_id", *attrs) \
        .withColumn("prev", F.lag(F.struct(*attrs)).over(w)) \
        .where(~F.col("prev").eqNullSafe(F.struct(*attrs)))  # null-safe: Roku never sends auto_renew
    dim_sub = (changed
               .withColumn("valid_to", F.lead("event_ts").over(w))
               .select(F.sha2(F.concat_ws("|", "subscription_id", "event_ts"), 256).substr(1, 16).alias("subscription_key"),
                       "subscription_id", *attrs, F.col("event_ts").alias("valid_from"), "valid_to",
                       F.col("valid_to").isNull().alias("is_current")))
    save(dim_sub, "dim_subscription")
    dim_sub = s.read.format("delta").load(table("gold", "dim_subscription"))

    # --- event fact (point-in-time join to the SCD2 version valid at the event) ------------
    rate = F.element_at(F.create_map(*[x for k, v in COMMISSION.items() for x in (F.lit(k), F.lit(v))]), F.col("e.channel"))
    fact = (ev.alias("e").join(dim_sub.alias("d"),
                               (F.col("e.subscription_id") == F.col("d.subscription_id")) &
                               (F.col("e.event_ts") >= F.col("d.valid_from")) &
                               (F.col("d.valid_to").isNull() | (F.col("e.event_ts") < F.col("d.valid_to"))), "left")
            .select("e.event_id", "e.channel", "d.subscription_key", "e.subscription_id", "e.event_type",
                    F.date_format("e.event_date", "yyyyMMdd").cast("int").alias("date_key"), "e.event_ts",
                    "e.plan_days", F.col("e.amount_twd").alias("gross_twd"),
                    (F.col("e.amount_twd") * (1 - rate)).cast("decimal(12,2)").alias("net_twd"),
                    "e.is_late", "e.ingest_date"))
    save(fact, "fact_subscription_event")
    fact = s.read.format("delta").load(table("gold", "fact_subscription_event"))  # reuse, don't recompute the join

    # --- daily active flag per subscription ------------------------------------------------
    first_seen = ev.groupBy("subscription_id").agg(F.min("event_date").alias("first_seen"))
    # Opening balance: a subscription whose first event in our data is a RENEW or CANCEL was already
    # active before we started seeing it. Treat it as active from before the window until
    # that renewal; otherwise every renewal on day one would count as a new signup.
    opening = (ev.withColumn("rn", F.row_number().over(w)).where("rn = 1 AND event_type IN ('RENEW', 'CANCEL')")
               .where(F.col("event_date") >= SNAPSHOT_START)
               .select("subscription_id", "channel", "plan_days",
                       F.date_sub(F.lit(SNAPSHOT_START), 1).alias("from_d"),
                       F.col("event_date").alias("seg_end_excl"), F.col("event_date").alias("active_until")))
    seg = (ev.withColumn("seg_end_excl", F.coalesce(F.lead("event_date").over(w), F.date_add(F.lit(end), 1)))
           .withColumn("active_until", F.when(F.col("event_type") == "REFUND", F.col("event_date"))
                       .otherwise(F.col("expires_date")))
           .withColumn("from_d", F.greatest("event_date", F.date_sub(F.lit(SNAPSHOT_START), 1)))
           .where(F.col("from_d") < F.col("seg_end_excl"))
           .select("subscription_id", "channel", "plan_days", "from_d", "seg_end_excl", "active_until")
           .unionByName(opening))
    daily = (seg.withColumn("date", F.explode(F.sequence("from_d", F.date_sub("seg_end_excl", 1))))
             .select("subscription_id", "date", "channel", "plan_days",
                     (F.col("date") < F.col("active_until")).alias("is_active"))
             .join(first_seen, "subscription_id"))
    wd = Window.partitionBy("subscription_id").orderBy("date")
    daily = (daily.withColumn("was_active", F.coalesce(F.lag("is_active").over(wd), F.lit(False)))
             .where(F.col("date") >= SNAPSHOT_START)
             .withColumn("movement",
                         F.when(F.col("is_active") & ~F.col("was_active") & (F.col("first_seen") == F.col("date")), "new")
                          .when(F.col("is_active") & ~F.col("was_active"), "reactivated")
                          .when(~F.col("is_active") & F.col("was_active"), "churned")))
    save(daily.drop("first_seen"), "fact_subscriber_daily")
    daily = s.read.format("delta").load(table("gold", "fact_subscriber_daily"))

    rev = (fact.where(F.col("event_type") != "CANCEL")
           .groupBy(F.to_date(F.col("event_ts")).alias("date"), "channel", "plan_days")
           .agg(F.sum("gross_twd").alias("gross_twd"), F.sum("net_twd").alias("net_twd")))
    mv = (daily.groupBy("date", "channel", "plan_days").agg(
            F.sum(F.col("is_active").cast("int")).alias("active_subs"),
            F.sum((F.col("movement") == "new").cast("int")).alias("new_subs"),
            F.sum((F.col("movement") == "reactivated").cast("int")).alias("reactivated_subs"),
            F.sum((F.col("movement") == "churned").cast("int")).alias("churned_subs"))
          .withColumn("net_adds", F.col("new_subs") + F.col("reactivated_subs") - F.col("churned_subs"))
          .join(rev, ["date", "channel", "plan_days"], "left").na.fill(0, ["gross_twd", "net_twd"]))
    save(mv, "agg_subscriber_movements")
    tot = mv.agg(*[F.sum(c).alias(c) for c in ["new_subs", "reactivated_subs", "churned_subs", "net_adds"]]).first()
    print(f"gold {end}: {dim_sub.count()} subscription versions, {fact.count()} fact events; "
          f"window totals new={tot.new_subs} reactivated={tot.reactivated_subs} churned={tot.churned_subs} net={tot.net_adds}")


if __name__ == "__main__":
    run(sys.argv[1])
