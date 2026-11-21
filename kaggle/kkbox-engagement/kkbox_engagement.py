# Runs on Kaggle: competition data + kkbox-pricing-mart's output. Phase 3 D: listening BEFORE the renewal date
# (Jan–Feb 2017, from the 30 GB user_logs.csv, streamed: never fully on disk) vs March churn.
import glob, json, shutil, subprocess
import numpy as np, pandas as pd
import pyarrow as pa, pyarrow.csv as pv, pyarrow.compute as pc

if not shutil.which("7z"):
    subprocess.run("apt-get update -qq && apt-get install -y -qq p7zip-full", shell=True, check=True)
OUT = "/kaggle/working"
SRC = glob.glob("/kaggle/input/**/user_logs.csv*", recursive=True)[0]
ROOT = glob.glob("/kaggle/input/**/gold/mart_pricing_user", recursive=True)[0].rsplit("/gold/", 1)[0]
pct = lambda v: f"{v:.2%}"

m = pd.read_parquet(f"{ROOT}/gold/mart_pricing_user",
                    columns=["msno", "is_churn", "step5", "expires_in_march", "pm", "price", "cur_tx_date"])
base = m[m.step5 & m.expires_in_march.fillna(False).astype(bool)].reset_index(drop=True)
ids = pa.array(base.msno.values)

# ---- stream: 7z -> stdout -> arrow CSV batches; keep Jan–Feb 2017 rows of base users as (user index, date)
src = subprocess.Popen(["7z", "e", "-so", SRC], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) if SRC.endswith(".7z") else None
reader = pv.open_csv(src.stdout if src else SRC, read_options=pv.ReadOptions(block_size=256 << 20),
                     convert_options=pv.ConvertOptions(include_columns=["msno", "date", "num_100", "num_unq", "total_secs"],
                                                       column_types={"msno": pa.string(), "date": pa.int32(), "num_100": pa.int64(),
                                                                     "num_unq": pa.int64(), "total_secs": pa.float64()}))
parts, rows = [], 0
for i, b in enumerate(reader):
    rows += b.num_rows
    t = pa.Table.from_batches([b])
    t = t.filter(pc.greater_equal(t["date"], 20170101))
    if t.num_rows:
        u = pc.index_in(t["msno"], value_set=ids)
        t = t.append_column("u", u).filter(pc.is_valid(u))
        d = pd.DataFrame({"u": t["u"].to_numpy(), "date": t["date"].to_numpy(),
                          "secs": np.clip(t["total_secs"].to_numpy(), 0, 86400), "full": t["num_100"].to_numpy()})
        parts.append(d.groupby(["u", "date"], as_index=False).sum())
    if i % 20 == 0:
        print(f"batch {i}: {rows:,} rows read", flush=True)
if src:
    assert src.wait() == 0, "7z failed"
print(f"total rows read: {rows:,}")
d = pd.concat(parts).groupby(["u", "date"], as_index=False).sum()
d["month"] = d.date // 100
g = d.groupby(["u", "month"]).agg(days=("date", "size"), secs=("secs", "sum")).unstack(fill_value=0)
f = pd.DataFrame(index=base.index)
for col, mo in [("jan", 201701), ("feb", 201702)]:
    f[f"{col}_days"] = g["days"].get(mo, pd.Series(dtype=float)).reindex(base.index).fillna(0)
    f[f"{col}_hours"] = g["secs"].get(mo, pd.Series(dtype=float)).reindex(base.index).fillna(0) / 3600
e = pd.concat([base, f], axis=1)

# cancel vs silent churn, same definition as kkbox-churn-drivers
led = pd.read_parquet(f"{ROOT}/silver/billing_ledger", columns=["msno", "transaction_date", "is_cancel"])
led = led[(led.is_cancel == 1)]
led["transaction_date"] = pd.to_datetime(led.transaction_date)
cx = led[led.transaction_date.between("2017-01-01", "2017-03-31")].merge(e[["msno", "cur_tx_date"]], on="msno")
cx = cx[cx.transaction_date >= pd.to_datetime(cx.cur_tx_date)]
e["cancelled"] = e.msno.isin(set(cx.msno))
e["churn_cancel"] = (e.is_churn == 1) & e.cancelled
e["churn_silent"] = (e.is_churn == 1) & ~e.cancelled

# ---- bands
e["feb_band"] = pd.cut(e.feb_days, [-1, 0, 7, 14, 21, 28], labels=["0 d", "1-7 d", "8-14 d", "15-21 d", "22-28 d"])
ratio = (e.feb_hours + 0.01) / (e.jan_hours + 0.01)
e["trend"] = np.select(
    [(e.jan_days == 0) & (e.feb_days == 0), (e.jan_days > 0) & (e.feb_days == 0), e.jan_days == 0,
     ratio < 0.5, ratio > 1.5],
    ["silent both months", "stopped in Feb", "started in Feb", "fell > 50%", "rose > 50%"], "steady (±50%)")

def tab(df, by):
    t = df.groupby(by, observed=True).agg(users=("msno", "size"), churn=("is_churn", "mean"),
                                         churn_cancel=("churn_cancel", "mean"), churn_silent=("churn_silent", "mean"))
    t["share_of_users"] = t.users / t.users.sum()
    return t
fb, tr = tab(e, "feb_band"), tab(e, "trend").sort_values("churn", ascending=False)
fb41 = tab(e[e.pm == 41], "feb_band")
fb.to_csv(f"{OUT}/engagement_feb_band.csv"); tr.to_csv(f"{OUT}/engagement_trend.csv")

# ---- early-warning flag: low or falling listening before the renewal date
e["flag"] = (e.feb_days <= 7) | e.trend.isin(["stopped in Feb", "fell > 50%"])
fl = e[e.flag]
ew = dict(flagged_share=e.flag.mean(), churn_flagged=fl.is_churn.mean(), churn_not_flagged=e[~e.flag].is_churn.mean(),
          lift=fl.is_churn.mean() / e.is_churn.mean(),
          share_of_cancel_churners_caught=fl.churn_cancel.sum() / e.churn_cancel.sum(),
          share_of_silent_churners_caught=fl.churn_silent.sum() / e.churn_silent.sum())
res = dict(rows_read=rows, base_users=len(e), with_any_jan_feb_listening=float(((e.jan_days + e.feb_days) > 0).mean()),
           feb_band=fb.round(4).to_dict(orient="index"), feb_band_pm41=fb41.round(4).to_dict(orient="index"),
           trend=tr.round(4).to_dict(orient="index"), early_warning=ew)

md = ["# Engagement before the renewal date (Phase 3 D)", "",
      f"Source: user_logs.csv, {rows:,} rows streamed; Jan–Feb 2017 kept for the {len(e):,} base users "
      f"(30-day, auto-renew, paid, standard tier, expiring in March). {res['with_any_jan_feb_listening']:.1%} listened at least once in Jan–Feb.",
      "All listening here happened before the 28 Feb cutoff, so it can be used to predict March churn.", "",
      "## Days listened in February vs March churn", "",
      "| Feb days | users | share | churn | via cancel | silent |", "|---|---|---|---|---|---|"]
md += [f"| {k} | {r.users:,} | {r.share_of_users:.0%} | {pct(r.churn)} | {pct(r.churn_cancel)} | {pct(r.churn_silent)} |" for k, r in fb.iterrows()]
md += ["", "Same, payment method 41 only (the pricing cohort):", "", "| Feb days | users | churn |", "|---|---|---|"]
md += [f"| {k} | {r.users:,} | {pct(r.churn)} |" for k, r in fb41.iterrows()]
md += ["", "## Listening trend, January → February", "",
       "| trend | users | share | churn | via cancel | silent |", "|---|---|---|---|---|---|"]
md += [f"| {k} | {r.users:,} | {r.share_of_users:.0%} | {pct(r.churn)} | {pct(r.churn_cancel)} | {pct(r.churn_silent)} |" for k, r in tr.iterrows()]
md += ["", "## Early-warning flag: ≤ 7 listening days in Feb, or listening stopped / fell by more than half", "",
       f"- Flags {ew['flagged_share']:.1%} of users; their churn {pct(ew['churn_flagged'])} vs {pct(ew['churn_not_flagged'])} for the rest "
       f"(lift {ew['lift']:.1f}×).",
       f"- Catches {ew['share_of_cancel_churners_caught']:.0%} of users who later cancelled and "
       f"{ew['share_of_silent_churners_caught']:.0%} of users who left silently."]

e[["msno", "jan_days", "feb_days", "jan_hours", "feb_hours", "feb_band", "trend", "flag"]].astype({"feb_band": str}).to_parquet(
    f"{OUT}/user_engagement.parquet", index=False)
json.dump(res, open(f"{OUT}/engagement.json", "w"), indent=2, default=str)
open(f"{OUT}/engagement.md", "w").write("\n".join(md) + "\n")
print("\n".join(md))
