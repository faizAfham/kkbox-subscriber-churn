# Runs on Kaggle: joins the pricing mart, churn flags and engagement into one slim user-level table for BigQuery/Looker Studio.
# One row per subscriber in the Phase 3 base (30-day, auto-renew, paid, standard tier, expiring March 2017).
import glob
import pandas as pd
g = lambda pat: glob.glob(f"/kaggle/input/**/{pat}", recursive=True)[0]
m = pd.read_parquet(g("gold/mart_pricing_user"))
base = m[m.step5 & m.expires_in_march.fillna(False).astype(bool)]
flags = pd.read_parquet(g("user_churn_flags.parquet"))
eng = pd.read_parquet(g("user_engagement.parquet"))
R = lambda p, c: p * (1 - (1 - c) ** 12) / c
t = (base[["msno", "is_churn", "price", "paid", "pm", "tenure_days", "tenure_band", "registered_via", "city", "price_rose"]]
     .merge(flags[["msno", "churn_cancel", "churn_silent"]], on="msno", how="left")
     .merge(eng[["msno", "feb_days", "feb_band", "trend", "flag"]], on="msno", how="left"))
tier_c = t.groupby("price").is_churn.mean()
t["value_12m_twd"] = [R(p, tier_c[p]) for p in t.price]          # worth of keeping this subscriber for a year
t["churn_type"] = t.churn_cancel.map({True: "cancelled"}).fillna(t.churn_silent.map({True: "silent"})).fillna("renewed")
t = t.rename(columns={"msno": "user_id", "pm": "payment_method", "flag": "low_listening_flag", "is_churn": "churned"})
t["price"] = t.price.astype(int); t["payment_method"] = t.payment_method.astype(int)
t["registered_via"] = t.registered_via.astype("Int64"); t["city"] = t.city.astype("Int64")
t = t.drop(columns=["churn_cancel", "churn_silent"])
assert t.user_id.is_unique and len(t) == len(base)
t.to_csv("/kaggle/working/kkbox_subscribers.csv.gz", index=False, compression="gzip")
print(len(t), t.dtypes, t.head(), sep="\n")
