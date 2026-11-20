"""One payload per channel goes through silver.parse and must come out identical.
run: .venv/bin/python tests/test_parse.py"""
import datetime as dt, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from common import spark
from generate_partner_events import to_payload
from silver import parse

ts = dt.datetime(2017, 3, 5, 18, 30, 0, tzinfo=dt.timezone.utc)  # 02:30 next day in Taipei
s = spark("test")
rows = [(json.dumps(to_payload(ch, "RENEW", "e1", "sub1", ts, 149, "30", dt.date(2017, 4, 4), True)), ch, dt.date(2017, 3, 6))
        for ch in ["direct", "apple", "roku", "amazon"]]
from pyspark.sql import functions as F
out = (parse(s.createDataFrame(rows, "raw_json string, channel string, ingest_date date"))
       .withColumn("ts_utc", F.date_format("event_ts", "yyyy-MM-dd HH:mm:ss")).collect())  # strings: collect() would shift to local tz

for r in out:
    got = (r.event_id, r.subscription_id, r.event_type, r.ts_utc, float(r.amount_raw), r.plan_days, r.expires_date)
    want = ("e1", "sub1", "RENEW", "2017-03-05 18:30:00", 149.0, 30, dt.date(2017, 4, 4))
    assert got == want, (r.channel, got)
    assert r.auto_renew in (True, None), r.channel  # Roku sends no auto-renew flag
print("ok: all 4 channels parse to the same row")
