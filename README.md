# subscriber-movements

A daily batch pipeline that turns messy billing webhooks from four channels (our own card
processor, Apple, Roku, Amazon) into one subscription ledger, a star schema, and a daily
"subscriber movements" table (active, new, reactivated, churned, net adds, revenue). It
also reconciles each partner's monthly payout report against the ledger.

Stack: PySpark 4.0, Delta Lake 4.0, Airflow 3.0, all running locally on one laptop.

```
landing/ (JSON webhooks per channel per day, payout CSVs)
   │  bronze.py      raw JSON string + ingest metadata, replaceWhere per day (idempotent)
   ▼
bronze.webhook_events
   │  silver.py      4 payload formats → 1 schema, UTC timestamps, refunds negative,
   │                 bad rows → quarantine, MERGE on (channel, event_id) blocks re-delivered webhooks
   ▼
silver.subscription_events  +  silver.quarantine
   │  dq.py silver   9 checks (uniqueness, nulls, sign convention, volume vs 7-day median ...)
   │  gold.py        dims + SCD2 subscription dim + facts + daily movements
   ▼
gold.dim_date / dim_channel / dim_plan / dim_subscription (SCD2)
gold.fact_subscription_event / fact_subscriber_daily / agg_subscriber_movements
   │  dq.py gold     revenue ties to silver, active(d) − active(d−1) = net_adds(d), no orphans
   │  reconcile.py   payout report vs ledger → matched / amount_mismatch / missing / unknown
   ▼
gold.recon_payout_detail / recon_payout_summary          dq.results (every check, every run)
```

Airflow DAG (`dags/subscriber_movements.py`): `bronze → silver → dq_silver → gold → dq_gold → is_recon_day → reconcile`,
`@daily`, catchup over 2017‑02‑28 … 2017‑04‑05, `max_active_runs=1` (one writer per Delta table).
A failed error-level check fails the task, so gold is never built from bad silver.

## Data

- **Real:** [KKBox churn challenge `transactions_v2`](https://data.mendeley.com/datasets/mv3f8bdrvy/1), a music streaming
  service's subscription transactions (Jan 2015 – Mar 2017). The Mendeley mirror holds 1,048,575 rows (it stops at
  Excel's row limit; the Kaggle original has ~1.43M). 906,706 subscribers, 37 payment methods.
- **Synthetic, built on top:** `generate_partner_events.py` maps payment methods to four billing channels and writes
  each transaction in that channel's own webhook format: Apple-style (ms epochs, milli-unit prices), Stripe-style
  (s epochs, minor units, nested objects), Roku-style (ISO time with +08:00 offset, decimal strings), Amazon-style
  (local time with **no** offset). It injects the problems real webhooks have:

| Injected problem | Rate | Caught by | Result in this run |
|---|---|---|---|
| Webhook re-delivered (same id, same day or up to 2 days later) | 2% | dropDuplicates + MERGE | 6,988 same-day + 14,018 cross-day dupes removed |
| Event arrives 1–5 days late | 3% | lands in correct `event_date`, flagged `is_late` | late rate 2.5% on a sample day (warn > 10%) |
| Missing amount on a paid event | 0.3% | quarantine | 3,129 rows quarantined (0.29%) |
| Paid event refunded later | 0.5% | REFUND event, negative amount | ends the subscription on the refund day |
| Partner omits a row / changes amount / pays something we never saw | 0.2% / 0.2% / 0.1% | reconcile.py | see below |

Totals: 1,074,305 webhooks landed over 37 daily runs → 1,050,170 unique events in silver.

## Results (March 2017)

- All 9 silver checks and 5 gold checks pass, including the movement identity
  (`active(d) − active(d−1) = new + reactivated − churned` on every day).
- **Partner reconciliation, March:**

| channel | rows | matched | amount mismatch | missing in partner report | unknown to us | our gross (TWD) | partner gross (TWD) | variance |
|---|---|---|---|---|---|---|---|---|
| amazon | 82,778 | 82,405 | 137 | 154 | 82 | 12,214,424 | 12,203,400 | −11,024 |
| apple | 91,250 | 90,843 | 170 | 146 | 91 | 17,798,699 | 17,781,554 | −17,145 |
| direct | 510,674 | 508,120 | 997 | 1,048 | 509 | 63,202,104 | 63,142,688 | −59,416 |
| roku | 71,212 | 70,831 | 151 | 160 | 70 | 20,059,921 | 20,025,684 | −34,237 |

  ~99.5% match on every channel. 1,508 rows (TWD 232,712) were billed by us but never paid by the partner: that is the chase list. Another 752 rows (TWD 112,048) were paid by partners for events we have no record of, which points to lost webhooks.

## Modeling decisions worth knowing

- **Opening balance.** KKBox `transactions_v2` is the challenge's churn cohort: members whose plan expired in
  March 2017. Most of them appear for the first time in March, *renewing*. Counting their first event as a
  signup gave 695K "new subscribers" in March, which is wrong. So a subscription whose first event
  is a RENEW/CANCEL is treated as already active before the window. After that fix, new signups in March = 0, and
  movements are reactivations and lapses only. That is what this cohort really is.
- **Churned = lapsed.** A subscription "churns" on the day it passes `expires_date` (or is refunded) without a
  renewal. KKBox's own label waits 30 days for a renewal; with one month of data I count gross lapses and
  report reactivations separately.
- **SCD2 on subscriptions.** A new version whenever channel, plan length or auto-renew changes. The comparison is
  null-safe because Roku never sends auto-renew. The fact table joins to the version valid at the event time.
- **Gold is a full rebuild** from silver (~2 min here). Past this size it should become an incremental MERGE
  over only the subscriptions that changed that day.
- **Timezones:** everything is stored in UTC. Amazon's offset-less local time is converted from Asia/Taipei.
- **Tuning:** caching silver inside gold (it feeds three outputs) and reading back the saved fact instead of
  recomputing its join took gold from over 10 min to 126 s on an 8 GB laptop.

## Run it

```bash
uv venv --python 3.12 .venv && uv pip install --python .venv -r requirements.txt
export JAVA_HOME=$(/usr/libexec/java_home -v 22)        # Java 17+ works
.venv/bin/python src/generate_partner_events.py          # needs data/raw/transactions_v2.csv (link above)
.venv/bin/python tests/test_parse.py                     # 4 channels → same row
.venv/bin/python src/run_range.py 2017-02-28 2017-04-05  # backfill without Airflow
.venv/bin/python src/dq.py gold 2017-03-31
.venv/bin/python src/reconcile.py 2017-03

# with Airflow (separate venv, so its pins never clash with Spark's)
uv venv --python 3.12 .venv-airflow && uv pip install --python .venv-airflow apache-airflow==3.0.6 \
  --constraint https://raw.githubusercontent.com/apache/airflow/constraints-3.0.6/constraints-3.12.txt
export AIRFLOW_HOME=$PWD/airflow_home AIRFLOW__CORE__DAGS_FOLDER=$PWD/dags AIRFLOW__CORE__LOAD_EXAMPLES=False
.venv-airflow/bin/airflow dags test subscriber_movements 2017-04-05   # one run
.venv-airflow/bin/airflow standalone                                  # UI at localhost:8080, unpause to backfill
```

Set `SLACK_WEBHOOK_URL` to get DQ failures posted to Slack.

## Limits

One month of real transactions, so there's no seasonality and no real signups. The partner channels and payout reports are
synthetic (the formats follow the public Apple/Stripe docs; Roku and Amazon are simplified). Commission rates are
flat assumptions. Runs on local Spark; nothing here has been tried on a cluster.
