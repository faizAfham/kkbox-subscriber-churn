# Runs on Kaggle on kkbox-pricing-mart's output. Phase 2 extras: (1) sensitivity of the verdict, (2) the pm39 anomaly.
import glob, json
import numpy as np, pandas as pd
from scipy.optimize import brentq

ROOT = glob.glob("/kaggle/input/**/gold/mart_pricing_user", recursive=True)[0].rsplit("/gold/", 1)[0]
OUT = "/kaggle/working"
m = pd.read_parquet(f"{ROOT}/gold/mart_pricing_user")
base = m[m.step5 & m.expires_in_march.fillna(False).astype(bool)]
coh = base[base.pm == 41]
R = lambda p, c: p * (1 - (1 - c) ** 12) / c
res, md = {}, ["# Pricing analysis: extras", ""]

# ---- 1. Sensitivity: does "149 pays" survive worse churn, or using what people actually paid?
c99, c149 = coh[coh.price == 99].is_churn.mean(), coh[coh.price == 149].is_churn.mean()
p_paid = coh.groupby("price").paid.mean()          # average actually paid on the expiring subscription
rows = []
for label, p99, p149 in [("list price", 99, 149), ("actually paid", p_paid[99], p_paid[149])]:
    for bump in [0, 0.01, 0.02, 0.03]:
        c = c149 + bump
        gap = R(p149, c) - R(p99, c99)
        be = brentq(lambda x: R(p149, x) - R(p99, c99), 1e-6, 0.999)
        rows.append(dict(price_basis=label, p99=round(p99, 1), p149=round(p149, 1), churn149=c,
                         R99=R(p99, c99), R149=R(p149, c), gap=gap, break_even=be, margin_pts=(be - c) * 100,
                         still_pays=bool(gap > 0 and be - c >= 0.01)))
s = pd.DataFrame(rows)
s.to_csv(f"{OUT}/sensitivity.csv", index=False)
# how bad would 149 churn have to get under each basis (already = break_even); also 99 churn falling
res["sensitivity"] = rows
md += ["## 1. Sensitivity of the verdict", "",
       f"Average actually paid on the expiring subscription: 99-tier {p_paid[99]:.1f}, 149-tier {p_paid[149]:.1f} TWD.", "",
       "| price basis | 149 churn | R(99) | R(149) | gap | break-even churn | margin (pts) | still 'pays'? |",
       "|---|---|---|---|---|---|---|---|"]
md += [f"| {r['price_basis']} | {r['churn149']:.2%} | {r['R99']:,.0f} | {r['R149']:,.0f} | {r['gap']:,.0f} | "
       f"{r['break_even']:.2%} | {r['margin_pts']:.1f} | {'yes' if r['still_pays'] else 'no'} |" for r in rows]

# ---- 2. The pm39 anomaly: 149 paid by pm39 churns ~54%. Why?
p39 = base[(base.pm == 39) & (base.price == 149)]
ref = base[(base.pm != 39) & (base.price == 149)]
def prof(df):
    return dict(users=len(df), churn=df.is_churn.mean(), discounted=df.is_discounted.mean(),
                paid_mean=df.paid.mean(), paid_zero=(df.paid == 0).mean(),
                tenure_median_days=df.tenure_days.median(), tenure_lt_1y=(df.tenure_days < 365).mean(),
                cancelled_in_march=(df.cancelled_in_march == 1).mean(),
                has_prev_price=df.prev_price.notna().mean(), listen_logs=df.listen_days_march.notna().mean(),
                registered_via_top=df.registered_via.value_counts(normalize=True).head(3).round(3).to_dict())
res["pm39_vs_other_149"] = {"pm39": prof(p39), "other_pm_149": prof(ref)}

# full payment history of these users from the ledger
cols = ["msno", "payment_method_id", "transaction_date", "plan_list_price", "actual_amount_paid",
        "payment_plan_days", "is_auto_renew", "is_cancel"]
led = pd.read_parquet(f"{ROOT}/silver/billing_ledger", columns=cols)
h = led[led.msno.isin(set(p39.msno))].copy()
h["transaction_date"] = pd.to_datetime(h.transaction_date)
h = h.sort_values(["msno", "transaction_date"])
first = h.groupby("msno").first()
pre = h[h.transaction_date <= pd.Timestamp("2017-02-28")]
mar = h[(h.transaction_date >= pd.Timestamp("2017-03-01")) & (h.transaction_date <= pd.Timestamp("2017-03-31"))]
hist = dict(
    first_tx_month_top=first.transaction_date.dt.to_period("M").astype(str).value_counts().head(6).to_dict(),
    first_tx_was_pm39=(first.payment_method_id == 39).mean(),
    pre_march_tx_per_user_median=pre.groupby("msno").size().median(),
    ever_paid_zero_before=(pre.groupby("msno").actual_amount_paid.min() == 0).mean(),
    pm39_tx_by_month=pre[pre.payment_method_id == 39].transaction_date.dt.to_period("M").astype(str)
        .value_counts().sort_index().tail(8).to_dict(),
    march_renewers=mar[mar.is_cancel == 0].msno.nunique(),
    march_renewers_pm_top=mar[mar.is_cancel == 0].payment_method_id.value_counts().head(5).to_dict(),
)
# pm39 at other prices: is it the method or the price?
other_prices = base[base.pm == 39].groupby("price").is_churn.agg(["size", "mean"]).round(4)
hist["pm39_by_price"] = other_prices.to_dict()
res["pm39_history"] = hist

a, b = res["pm39_vs_other_149"]["pm39"], res["pm39_vs_other_149"]["other_pm_149"]
md += ["", "## 2. Why does 149 via pm39 churn so much?", "",
       "| | pm39 @149 | other methods @149 |", "|---|---|---|"]
for k in ["users", "churn", "discounted", "paid_mean", "paid_zero", "tenure_median_days", "tenure_lt_1y",
          "cancelled_in_march", "has_prev_price", "listen_logs"]:
    fa = (lambda v: f"{v:,.0f}" if k in ("users", "tenure_median_days") else (f"{v:.1f}" if k == "paid_mean" else f"{v:.1%}"))
    md.append(f"| {k} | {fa(a[k])} | {fa(b[k])} |")
md += ["", f"- registered_via (top 3) pm39: {a['registered_via_top']} vs others: {b['registered_via_top']}",
       f"- first transaction month (top): {hist['first_tx_month_top']}",
       f"- first transaction was pm39: {hist['first_tx_was_pm39']:.1%}; ever paid 0 before March: {hist['ever_paid_zero_before']:.1%}",
       f"- pm39 transactions by month (last 8): {hist['pm39_tx_by_month']}",
       f"- March renewers: {hist['march_renewers']:,}; their payment methods: {hist['march_renewers_pm_top']}",
       f"- pm39 churn at other prices: {hist['pm39_by_price']}"]

json.dump(res, open(f"{OUT}/extras.json", "w"), indent=2, default=str)
open(f"{OUT}/extras.md", "w").write("\n".join(md) + "\n")
print("\n".join(md))
