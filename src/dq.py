"""Automated data quality checks, Deequ-style: each check measures one number and
compares it to a threshold. Every result is appended to data/lake/dq/results, so you get
a history to chart. Any failed `error` check raises, which fails the Airflow task and
stops bad data from reaching gold. A failed `warn` check only gets logged and alerted.

usage: python src/dq.py silver 2017-03-05
       python src/dq.py gold   2017-03-31
"""
import datetime as dt, json, os, sys, urllib.request
from pyspark.sql import functions as F
from common import exists, spark, table

EVENT_TYPES = ["NEW", "RENEW", "CANCEL", "REFUND"]


def check(name, observed, ok, threshold, severity="error"):
    return {"check": name, "observed": float(observed), "threshold": threshold, "passed": bool(ok), "severity": severity}


def silver_checks(s, ds):
    bronze = s.read.format("delta").load(table("bronze", "webhook_events"))
    ev = s.read.format("delta").load(table("silver", "subscription_events"))
    q = s.read.format("delta").load(table("silver", "quarantine"))
    today = ev.where(F.col("ingest_date") == ds)
    n_in = bronze.where(F.col("ingest_date") == ds).count()
    n_q = q.where(F.col("ingest_date") == ds).count()
    n_today = today.count()
    dup = ev.groupBy("channel", "event_id").count().where("count > 1").count()
    nulls = today.where(F.col("subscription_id").isNull() | F.col("event_ts").isNull() | F.col("amount_twd").isNull()).count()
    bad_type = today.where(~F.col("event_type").isin(EVENT_TYPES)).count()
    bad_sign = today.where(((F.col("event_type") == "REFUND") & (F.col("amount_twd") >= 0)) |
                           ((F.col("event_type") != "REFUND") & (F.col("amount_twd") < 0))).count()
    late = today.where("is_late").count()
    future = today.where(F.col("event_date") > F.col("ingest_date")).count()
    # volume vs trailing 7 days (skip the one-off backfill day)
    hist = [r["n"] for r in bronze.where((F.col("ingest_date") < ds) &
                                         (F.col("ingest_date") >= F.date_sub(F.lit(ds), 7)) &
                                         (F.col("ingest_date") > "2017-02-28"))
            .groupBy("ingest_date").agg(F.count("*").alias("n")).collect()]
    med = sorted(hist)[len(hist) // 2] if hist else None
    ratio = n_in / med if med else 1.0
    return [
        check("bronze_rows_landed", n_in, n_in > 0, "> 0"),
        check("quarantine_rate", n_q / max(n_in, 1), n_q / max(n_in, 1) <= 0.01, "<= 1%"),
        check("unique_channel_event_id", dup, dup == 0, "= 0 duplicates"),
        check("not_null_keys", nulls, nulls == 0, "= 0"),
        check("event_type_in_set", bad_type, bad_type == 0, "= 0"),
        check("refund_sign_convention", bad_sign, bad_sign == 0, "= 0"),
        check("no_future_events", future, future == 0, "= 0"),
        check("late_event_rate", late / max(n_today, 1), late / max(n_today, 1) <= 0.10, "<= 10%", "warn"),
        check("volume_vs_7d_median", ratio, 0.5 <= ratio <= 2.0, "0.5x to 2x", "warn"),
    ]


def gold_checks(s, end):
    g = lambda n: s.read.format("delta").load(table("gold", n))
    fact, mv, daily = g("fact_subscription_event"), g("agg_subscriber_movements"), g("fact_subscriber_daily")
    silver = s.read.format("delta").load(table("silver", "subscription_events")).where(F.col("event_date") <= end)
    orphan = fact.where(F.col("subscription_key").isNull()).count()
    diff = abs(float(fact.agg(F.sum("gross_twd")).first()[0] or 0) - float(silver.agg(F.sum("amount_twd")).first()[0] or 0))
    # movement identity: active(d) - active(d-1) must equal net_adds(d) for every day after the first
    by_day = mv.groupBy("date").agg(F.sum("active_subs").alias("a"), F.sum("net_adds").alias("n")).orderBy("date").collect()
    broken = sum(1 for p, c in zip(by_day, by_day[1:]) if c.a - p.a != c.n)
    dup_day = daily.groupBy("subscription_id", "date").count().where("count > 1").count()
    return [
        check("fact_has_subscription_key", orphan, orphan == 0, "= 0 orphans"),
        check("revenue_ties_to_silver", diff, diff < 0.01, "|diff| < 0.01 TWD"),
        check("movement_identity_holds", broken, broken == 0, "= 0 broken days"),
        check("one_row_per_sub_day", dup_day, dup_day == 0, "= 0"),
        check("snapshot_reaches_end_date", 1 if by_day and str(by_day[-1].date) == end else 0,
              bool(by_day) and str(by_day[-1].date) == end, "last day = run date"),
    ]


def alert(msg):
    """Post to Slack if SLACK_WEBHOOK_URL is set, else just print."""
    print("ALERT:", msg)
    url = os.environ.get("SLACK_WEBHOOK_URL")
    if url:
        urllib.request.urlopen(urllib.request.Request(url, json.dumps({"text": msg}).encode(),
                                                      {"Content-Type": "application/json"}), timeout=10)


def run(layer, ds):
    s = spark(f"dq-{layer}")
    results = (silver_checks if layer == "silver" else gold_checks)(s, ds)
    rows = [{**r, "layer": layer, "run_date": ds, "checked_at": dt.datetime.now(dt.timezone.utc).isoformat()}
            for r in results]
    s.createDataFrame(rows).write.format("delta").mode("append").save(table("dq", "results"))
    for r in results:
        print(f"  {'PASS' if r['passed'] else 'FAIL'} [{r['severity']}] {r['check']}: {r['observed']:g} (want {r['threshold']})")
    failed = [r for r in results if not r["passed"]]
    if failed:
        alert(f"DQ {layer} {ds}: " + ", ".join(f"{r['check']}={r['observed']:g}" for r in failed))
    if any(r["severity"] == "error" for r in failed):
        raise SystemExit(f"DQ {layer} {ds}: error-level check failed, stopping the pipeline")
    return results


if __name__ == "__main__":
    run(sys.argv[1], sys.argv[2])
