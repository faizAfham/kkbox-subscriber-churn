# Runs on Kaggle on kkbox-pricing-mart's output. Two follow-up checks for Phase 3:
# 1) are the cancels clustered on a few dates (system-made, e.g. a payment method being retired) or spread out (user-made)?
# 2) inside payment method 41, is 99 a different sign-up channel's product than 149?
import glob
import pandas as pd
ROOT = glob.glob("/kaggle/input/**/gold/mart_pricing_user", recursive=True)[0].rsplit("/gold/", 1)[0]
m = pd.read_parquet(f"{ROOT}/gold/mart_pricing_user")
base = m[m.step5 & m.expires_in_march.fillna(False).astype(bool)]
led = pd.read_parquet(f"{ROOT}/silver/billing_ledger", columns=["msno", "payment_method_id", "transaction_date", "is_cancel"])
led = led[(led.is_cancel == 1) & led.msno.isin(set(base.msno))]
led["transaction_date"] = pd.to_datetime(led.transaction_date)
c = led[led.transaction_date.between("2017-01-01", "2017-03-31")].merge(base[["msno", "pm", "is_churn"]], on="msno")
md = ["# Phase 3 checks", "", "## 1. Cancel dates, Jan–Mar 2017 (base users)", ""]
for pm in [39, 41, 40, 30, 36]:
    s = c[c.pm == pm].transaction_date.dt.date.value_counts()
    md.append(f"- pm {pm}: {len(c[c.pm == pm]):,} cancels on {s.size} distinct days; top 3 days hold {s.head(3).sum() / max(s.sum(), 1):.0%}: "
              f"{ {str(k): int(v) for k, v in s.head(3).items()} }")
s = c.payment_method_id.value_counts().head(5)
md.append(f"- method recorded on the cancel row (all base): { {int(k): int(v) for k, v in s.items()} }")
w = c.groupby(c.transaction_date.dt.to_period('W')).size()
md += ["", "Cancels per week (all base users):", "", "```", w.to_string(), "```", "",
       "## 2. Inside payment method 41: sign-up channel by price", "", "```",
       pd.crosstab(base[base.pm == 41].registered_via, base[base.pm == 41].price).to_string(), "```", "",
       "Churn by price × channel inside pm41 (cells ≥ 1,000 users):", "", "```"]
g = base[base.pm == 41].groupby(["registered_via", "price"]).is_churn.agg(["size", "mean"])
md += [g[g["size"] >= 1000].round(4).to_string(), "```"]
open("/kaggle/working/checks.md", "w").write("\n".join(md) + "\n")
print("\n".join(md))
