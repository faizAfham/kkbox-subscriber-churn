"""Local backfill without Airflow: bronze + silver for each day, then gold once.
usage: python src/run_range.py 2017-02-28 2017-04-05"""
import datetime as dt, sys
import bronze, silver, gold

a, b = (dt.date.fromisoformat(x) for x in sys.argv[1:3])
for i in range((b - a).days + 1):
    d = str(a + dt.timedelta(days=i))
    if bronze.run(d):
        silver.run(d)
gold.run(str(min(b, dt.date(2017, 3, 31))))
