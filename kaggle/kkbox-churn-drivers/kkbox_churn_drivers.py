# Runs on Kaggle on kkbox-pricing-mart's output. Phase 3: where is KKBox losing paying subscribers, and what to fix first?
# A churn breakdown (cancelled vs silent), B silent churn by payment method, C what the price tiers really are,
# E sizing, F experiment design. Engagement (D) is its own notebook because it streams the 30 GB log file.
import glob, json
import numpy as np, pandas as pd
from statsmodels.stats.power import NormalIndPower
from statsmodels.stats.proportion import proportion_effectsize

ROOT = glob.glob("/kaggle/input/**/gold/mart_pricing_user", recursive=True)[0].rsplit("/gold/", 1)[0]
OUT = "/kaggle/working"
R = lambda p, c: p * (1 - (1 - c) ** 12) / c       # 12-month revenue per subscriber at monthly churn c
pct = lambda v: f"{v:.2%}"
res, md = {}, ["# Churn drivers (Phase 3)", ""]

m = pd.read_parquet(f"{ROOT}/gold/mart_pricing_user")
for c in ["cur_tx_date", "cur_expire", "first_tx_date"]:
    m[c] = pd.to_datetime(m[c])
led = pd.read_parquet(f"{ROOT}/silver/billing_ledger", columns=[
    "msno", "payment_method_id", "transaction_date", "membership_expire_date", "plan_list_price",
    "actual_amount_paid", "payment_plan_days", "is_auto_renew", "is_cancel"])
led["transaction_date"] = pd.to_datetime(led.transaction_date)
led["membership_expire_date"] = pd.to_datetime(led.membership_expire_date)

# ---- user flags: did the user press cancel on the expiring subscription? what method did renewers use?
cx = led[(led.is_cancel == 1) & led.transaction_date.between("2017-01-01", "2017-03-31")][["msno", "transaction_date"]]
cx = cx.merge(m[["msno", "cur_tx_date"]], on="msno")
cancelled = set(cx[cx.transaction_date >= cx.cur_tx_date].msno)   # a cancel on/after the expiring subscription
m["cancelled"] = m.msno.isin(cancelled)
m["churn_cancel"] = (m.is_churn == 1) & m.cancelled
m["churn_silent"] = (m.is_churn == 1) & ~m.cancelled       # left without pressing cancel
cur_cancel = led[led.is_cancel == 1][["msno", "transaction_date", "membership_expire_date"]].merge(
    m[["msno", "cur_tx_date", "cur_expire"]], left_on=["msno", "transaction_date", "membership_expire_date"],
    right_on=["msno", "cur_tx_date", "cur_expire"])
mar = led[led.transaction_date.between("2017-03-01", "2017-03-31") & (led.is_cancel == 0)]
renew_pm = mar.sort_values("transaction_date").groupby("msno").payment_method_id.last().rename("renew_pm")
m = m.merge(renew_pm, left_on="msno", right_index=True, how="left")

exp = m[m.step2 & m.expires_in_march.fillna(False).astype(bool)]            # 30-day plans expiring in March
base = m[m.step5 & m.expires_in_march.fillna(False).astype(bool)]           # + auto-renew, paid, standard tier
res["dq"] = dict(expiring_row_is_a_cancel=int(cur_cancel.msno.isin(base.msno).sum()), base_users=len(base))

# ---- A. churn breakdown
def brk(df):
    n = len(df)
    return dict(users=n, churn=df.is_churn.mean(), churn_cancel=df.churn_cancel.mean(), churn_silent=df.churn_silent.mean(),
                silent_share=df.churn_silent.sum() / max(df.is_churn.sum(), 1))
a = {f"auto_renew={int(k)}": brk(g) for k, g in exp.groupby("auto_renew")}
a["base (auto-renew, paid, tier)"] = brk(base)
a.update({f"base, price {p}": brk(g) for p, g in base.groupby("price")})
res["A_breakdown"] = a
md += ["## A. Churn breakdown: pressed cancel vs left without cancelling", "",
       "30-day plans expiring in March 2017. 'Silent' = churned with no cancel on or after the expiring subscription.",
       "For auto-renew users a silent exit means the renewal charge did not go through (or the method stopped working);",
       "for manual-renew users it just means they did not pay again.", "",
       "| group | users | churn | via cancel | silent | silent share of churn |", "|---|---|---|---|---|---|"]
md += [f"| {k} | {v['users']:,} | {pct(v['churn'])} | {pct(v['churn_cancel'])} | {pct(v['churn_silent'])} | {v['silent_share']:.0%} |"
       for k, v in a.items()]
md += ["", f"DQ: {res['dq']['expiring_row_is_a_cancel']:,} of {len(base):,} base users have a cancel row as their expiring subscription."]

# ---- B. silent churn by payment method
feb = led[led.transaction_date.between("2017-02-01", "2017-02-28") & (led.is_cancel == 0)].payment_method_id.value_counts()
marv = mar.payment_method_id.value_counts()
idx = (marv / feb) / (marv.sum() / feb.sum())               # March volume vs February, relative to all methods
def pm_row(g):
    ren = g[(g.is_churn == 0) & g.renew_pm.notna()]
    return pd.Series(dict(users=len(g), churn=g.is_churn.mean(), churn_cancel=g.churn_cancel.mean(),
                          churn_silent=g.churn_silent.mean(), renewers_with_march_tx=len(ren),
                          renewers_switched_method=(ren.renew_pm != ren.pm).mean() if len(ren) else np.nan,
                          mean_list_price=g.price.mean(), tenure_median_days=g.tenure_days.median()))
pmt = base.groupby("pm").apply(pm_row)
pmt = pmt[pmt.users >= 1000].copy()
pmt["march_volume_index"] = idx.reindex(pmt.index)
s0 = base.churn_silent.mean()
pmt["silent_vs_avg"] = pmt.churn_silent / s0
pmt = pmt.sort_values("churn_silent", ascending=False)
pmt.to_csv(f"{OUT}/pm_table.csv")
at_risk = pmt[(pmt.silent_vs_avg >= 2)].index.tolist()
res["B_payment"] = dict(avg_silent=s0, at_risk_methods=at_risk, table=pmt.round(4).to_dict(orient="index"))
md += ["", "## B. Silent churn by payment method (base, methods with ≥ 1,000 users)", "",
       f"Average silent churn: {pct(s0)}. 'At risk' = silent churn ≥ 2× average: {at_risk}.",
       "March volume index: the method's March/Feb transaction ratio divided by the ratio for all methods (1.0 = normal; near 0 = the method stopped being used).", "",
       "| pm | users | churn | via cancel | silent | × avg | renewers who switched method | March volume index | median tenure (d) |",
       "|---|---|---|---|---|---|---|---|---|"]
md += [f"| {p} | {r.users:,.0f} | {pct(r.churn)} | {pct(r.churn_cancel)} | {pct(r.churn_silent)} | {r.silent_vs_avg:.1f} | "
       f"{r.renewers_switched_method:.0%} | {r.march_volume_index:.2f} | {r.tenure_median_days:,.0f} |" for p, r in pmt.iterrows()]

# ---- C. what are the price tiers? (pricing reframe: are 99/100/129/149 the same product at different prices?)
def top(s, k=3):
    return ", ".join(f"{i} ({v:.0%})" for i, v in s.value_counts(normalize=True).head(k).items())
tp = []
for p, g in base.groupby("price"):
    tp.append(dict(price=p, users=len(g), top_payment_methods=top(g.pm), top_signup_channels=top(g.registered_via, 2),
                   discounted=g.is_discounted.mean(), paid_mean=g.paid.mean(), tenure_median_days=g.tenure_days.median(),
                   prev_price_same=(g.prev_price == p).mean(), has_prev=g.prev_price.notna().mean(), churn=g.is_churn.mean()))
tp = pd.DataFrame(tp).set_index("price")
tp.to_csv(f"{OUT}/tier_profile.csv")
tr = base[base.prev_price.notna()]
trans = pd.crosstab(tr.prev_price.where(tr.prev_price.isin([99, 100, 129, 149, 180]), -1), tr.price, normalize="index")
pm_price = pd.crosstab(base.pm, base.price)
pm_price = pm_price[pm_price.sum(axis=1) >= 1000]
shared = {int(pm): row[row > 0].index.tolist() for pm, row in pm_price.iterrows()}
res["C_tiers"] = dict(profile=tp.round(4).to_dict(orient="index"), prev_to_cur=trans.round(3).to_dict(),
                      prices_per_method=shared)
md += ["", "## C. What the price tiers are (pricing reframe)", "",
       "| price | users | top payment methods | top sign-up channels | discounted | mean paid | median tenure | prev 30-day price was the same | churn |",
       "|---|---|---|---|---|---|---|---|---|"]
md += [f"| {p} | {r.users:,} | {r.top_payment_methods} | {r.top_signup_channels} | {r.discounted:.0%} | {r.paid_mean:.1f} | "
       f"{r.tenure_median_days:,.0f} | {r.prev_price_same:.0%} of {r.has_prev:.0%} with one | {pct(r.churn)} |" for p, r in tp.iterrows()]
md += ["", "Previous 30-day price → current price (row-normalised; -1 = some other price):", "", "```\n" + trans.round(3).to_string() + "\n```", "",
       "Prices offered per payment method (methods with ≥ 1,000 base users):", ""]
md += [f"- pm {pm}: {v}" for pm, v in shared.items()]

# ---- E. sizing: TWD at stake per monthly expiring cohort
tier_c = base.groupby("price").is_churn.mean()
base = base.assign(value_if_kept=[R(p, tier_c[p]) for p in base.price])
sil_val, can_val = base[base.churn_silent].value_if_kept.sum(), base[base.churn_cancel].value_if_kept.sum()
risk = base[base.pm.isin(at_risk)]
risk_val = risk[risk.churn_silent].value_if_kept.sum()
# price lever: new paid 30-day subscriptions per month by first paid price (Sep 2016 – Feb 2017)
paid = led[(led.plan_list_price > 0) & (led.payment_plan_days == 30) & (led.is_cancel == 0)]
fp = paid.sort_values("transaction_date").groupby("msno").first()
fp = fp[fp.transaction_date.between("2016-09-01", "2017-02-28")]
starts = fp.groupby([fp.transaction_date.dt.to_period("M"), "plan_list_price"]).size().unstack(fill_value=0)
starts99 = starts.get(99, pd.Series(0)).mean()
R99, R149 = R(99, tier_c[99]), R(149, tier_c[149])
conv_be = 1 - R99 / R149                      # 149 still pays unless it loses more than this share of would-be sign-ups
rows = [dict(lever="silent churn, all methods", users_per_month=int(base.churn_silent.sum()), twd_12m_per_cohort=sil_val),
        dict(lever="silent churn, at-risk methods", users_per_month=int(risk.churn_silent.sum()), twd_12m_per_cohort=risk_val),
        dict(lever="churn via cancel", users_per_month=int(base.churn_cancel.sum()), twd_12m_per_cohort=can_val),
        dict(lever="new 99 sign-ups moved to 149 (no lost sign-ups)", users_per_month=int(starts99),
             twd_12m_per_cohort=starts99 * (R149 - R99))]
for rec in [0.10, 0.25, 0.50]:
    rows.append(dict(lever=f"recover {rec:.0%} of silent churn, at-risk methods", users_per_month=int(risk.churn_silent.sum() * rec),
                     twd_12m_per_cohort=risk_val * rec))
sz = pd.DataFrame(rows)
sz["twd_per_year_if_every_month_like_march"] = sz.twd_12m_per_cohort * 12
sz.to_csv(f"{OUT}/sizing.csv", index=False)
res["E_sizing"] = dict(rows=rows, new_paid_starts_per_month=starts.mean().round(0).to_dict(), conversion_break_even=conv_be)
md += ["", "## E. Sizing: what each problem is worth", "",
       "Value of keeping one subscriber = their tier's 12-month revenue R(p, c). Per monthly expiring cohort; ×12 assumes every month looks like March.", "",
       "| lever | users / month | TWD (12 m) per cohort | TWD / year if every month is like March |", "|---|---|---|---|"]
md += [f"| {x.lever} | {x.users_per_month:,} | {x.twd_12m_per_cohort:,.0f} | {x.twd_per_year_if_every_month_like_march:,.0f} |" for x in sz.itertuples()]
md += ["", f"New paid 30-day subscriptions per month by first price (Sep 2016 – Feb 2017 average): "
       f"{ {int(k): int(v) for k, v in starts.mean().round(0).items() if k in (99, 100, 129, 149, 180)} }",
       f"- Price lever: 149 earns more than 99 unless it loses more than **{conv_be:.0%}** of the people who would have signed up at 99 "
       f"(1 − R99/R149 = 1 − {R99:,.0f}/{R149:,.0f}). This dataset cannot see sign-up conversion; only a test can."]

# ---- F. experiment design: sample size and duration for the two candidate tests
pw = NormalIndPower()
n_for = lambda p0, p1: int(np.ceil(pw.solve_power(proportion_effectsize(p1, p0), power=0.8, alpha=0.05)))
ex = []
c_risk = risk.is_churn.mean() if len(risk) else np.nan
for rel in [0.10, 0.20, 0.30]:
    if len(risk):
        n = n_for(c_risk, c_risk * (1 - rel))
        ex.append(dict(test="1. payment recovery (at-risk methods)", baseline_churn=c_risk, target_churn=c_risk * (1 - rel),
                       n_per_arm=n, eligible_per_month=len(risk), months_to_fill=2 * n / len(risk)))
c149 = tier_c[149]
new_flow = starts.get(99, pd.Series(0)).mean() + starts.get(149, pd.Series(0)).mean()
for d in [0.005, 0.01, 0.02]:
    n = n_for(c149, c149 + d)
    ex.append(dict(test="2. price 149 vs 99 on new sign-ups", baseline_churn=c149, target_churn=c149 + d,
                   n_per_arm=n, eligible_per_month=int(new_flow), months_to_fill=2 * n / new_flow))
ext = pd.DataFrame(ex)
ext.to_csv(f"{OUT}/experiment_sizes.csv", index=False)
res["F_experiments"] = ex
md += ["", "## F. Experiment sizes (80% power, α = 0.05, two-sided, user-level randomisation)", "",
       "| test | baseline churn | detect churn of | users per arm | eligible users / month | months to fill both arms |", "|---|---|---|---|---|---|"]
md += [f"| {x.test} | {pct(x.baseline_churn)} | {pct(x.target_churn)} | {x.n_per_arm:,} | {x.eligible_per_month:,} | {x.months_to_fill:.1f} |"
       for x in ext.itertuples()]

m[["msno", "cancelled", "churn_cancel", "churn_silent", "renew_pm"]].to_parquet(f"{OUT}/user_churn_flags.parquet", index=False)
json.dump(res, open(f"{OUT}/drivers.json", "w"), indent=2, default=str)
open(f"{OUT}/drivers.md", "w").write("\n".join(md) + "\n")
print("\n".join(md))
