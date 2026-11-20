# Runs on Kaggle on kkbox-pricing-mart's output. Phase 2: applies analysis/decision_rule.md exactly as committed.
import glob, json
import numpy as np, pandas as pd
from scipy.optimize import brentq
from statsmodels.stats.proportion import proportion_confint
from statsmodels.stats.contingency_tables import StratifiedTable
from statsmodels.stats.power import NormalIndPower
from statsmodels.stats.proportion import proportion_effectsize

MART = glob.glob("/kaggle/input/**/gold/mart_pricing_user", recursive=True)[0]
OUT = "/kaggle/working"
m = pd.read_parquet(MART)
base = m[m.step5 & m.expires_in_march.fillna(False).astype(bool)]          # tiers, any payment method
coh = base[base.pm == 41]                                        # the decision-rule cohort
rng = np.random.default_rng(42)
R = lambda p, c: p * (1 - (1 - c) ** 12) / c                     # 12-month revenue per starting subscriber
res, md = {}, ["# Pricing analysis (Phase 2)", ""]


def rate_table(df, by):
    g = df.groupby(by).agg(users=("msno", "size"), churned=("is_churn", "sum"),
                           cancelled=("cancelled_in_march", lambda s: (s == 1).sum()),
                           downgraded=("downgraded", lambda s: (s == True).sum()))
    g["churn"] = g.churned / g.users
    lo, hi = proportion_confint(g.churned, g.users, method="wilson")
    g["churn_lo"], g["churn_hi"] = lo, hi
    g["cancel"], g["downgrade"] = g.cancelled / g.users, g.downgraded / g.users
    return g


# 1. churn and revenue by tier, inside the cohort
t = rate_table(coh, "price")
t["R_12m"] = [R(p, c) for p, c in zip(t.index, t.churn)]
t.to_csv(f"{OUT}/tier_table.csv")
md += ["## 1. Cohort (pm41, 30-day auto-renew, expiring in March): churn and 12-month revenue by tier", "",
       f"Cohort size: {len(coh):,} users (step 7 of the funnel).", "",
       "| price | users | churn | 95% CI | cancel | downgrade | R (12 m, TWD) |", "|---|---|---|---|---|---|---|"]
md += [f"| {p} | {r.users:,} | {r.churn:.2%} | {r.churn_lo:.2%}–{r.churn_hi:.2%} | {r.cancel:.2%} | {r.downgrade:.2%} | {r.R_12m:,.0f} |"
       for p, r in t.iterrows()]

# 2. bootstrap the R gap 149 vs 99 (resampling Bernoulli outcomes = binomial draws per tier)
n99, n149 = int(t.loc[99, "users"]), int(t.loc[149, "users"])
c99, c149 = t.loc[99, "churn"], t.loc[149, "churn"]
B = 10_000
b99, b149 = rng.binomial(n99, c99, B) / n99, rng.binomial(n149, c149, B) / n149
gap = R(149, b149) - R(99, b99)
gap_lo, gap_hi = np.percentile(gap, [2.5, 97.5])
c_be = brentq(lambda c: R(149, c) - R(99, c99), 1e-6, 0.999)   # churn at which 149 earns what 99 earns
margin = c_be - c149
if R(149, c149) < R(99, c99):
    verdict = "3. Don't raise: 149 earns less than 99. Find out why 149 users leave."
elif gap_lo > 0 and margin >= 0.01:
    verdict = "1. 149 pays: propose a price test that moves new subscribers to 149."
else:
    verdict = "2. Too close to call: run the price test before deciding."
res["rule"] = dict(R99=R(99, c99), R149=R(149, c149), gap=R(149, c149) - R(99, c99), gap_ci=[gap_lo, gap_hi],
                   c99=c99, c149=c149, break_even_churn=c_be, margin_pts=margin * 100, verdict=verdict)
md += ["", "## 2. The decision rule", "",
       f"- R(99) = {R(99, c99):,.0f}, R(149) = {R(149, c149):,.0f}, gap = {R(149, c149) - R(99, c99):,.0f} TWD "
       f"(bootstrap 95% CI {gap_lo:,.0f} to {gap_hi:,.0f}).",
       f"- Break-even churn for 149 = {c_be:.2%}; observed 149 churn = {c149:.2%}; margin = {margin * 100:.1f} points.",
       f"- **Verdict: {verdict}**"]

# 3. confounder: tenure bands
bands = ["<1y", "1-2y", ">2y"]
two = coh[coh.price.isin([99, 149])]
tb = rate_table(two, ["tenure_band", "price"])
tb.to_csv(f"{OUT}/tenure_table.csv")
tables = []
for b in bands:
    s = two[two.tenure_band == b]
    a = ((s.price == 149) & (s.is_churn == 1)).sum(); bb = ((s.price == 149) & (s.is_churn == 0)).sum()
    c = ((s.price == 99) & (s.is_churn == 1)).sum(); d = ((s.price == 99) & (s.is_churn == 0)).sum()
    tables.append(np.array([[a, bb], [c, d]]))
st = StratifiedTable(tables)
crude_or = (two[(two.price == 149)].is_churn.mean() / (1 - c149)) / (c99 / (1 - c99))
w = two.tenure_band.value_counts(normalize=True)                # direct standardisation on the pooled mix
adj_gap = sum(w[b] * (tb.loc[(b, 149), "churn"] - tb.loc[(b, 99), "churn"]) for b in bands)
crude_gap = c149 - c99
shrink = 1 - adj_gap / crude_gap if crude_gap else float("nan")
res["tenure"] = dict(crude_gap_pts=crude_gap * 100, adjusted_gap_pts=adj_gap * 100, shrink=shrink,
                     crude_or=crude_or, mh_or=st.oddsratio_pooled, mh_or_ci=list(st.oddsratio_pooled_confint()),
                     tenure_explains_most=bool(shrink > 0.5))
md += ["", "## 3. Confounder check: tenure", "", "| tenure | price | users | churn |", "|---|---|---|---|"]
md += [f"| {b} | {p} | {r.users:,} | {r.churn:.2%} |" for (b, p), r in tb.iterrows()]
md += ["", f"- Crude churn gap 149 − 99 = {crude_gap * 100:.2f} pts; tenure-standardised gap = {adj_gap * 100:.2f} pts "
       f"(shrinks {shrink:.0%}).",
       f"- Odds ratio crude {crude_or:.2f} → Mantel-Haenszel {st.oddsratio_pooled:.2f} "
       f"(95% CI {st.oddsratio_pooled_confint()[0]:.2f}–{st.oddsratio_pooled_confint()[1]:.2f}).",
       f"- Rule: tenure explains most of the gap? **{'Yes' if shrink > 0.5 else 'No'}**"]

# 4. what would change my mind: users whose price rose
pr = coh[coh.price_rose == True]
pr_c = pr.is_churn.mean() if len(pr) else float("nan")
lo, hi = proportion_confint(pr.is_churn.sum(), len(pr), method="wilson") if len(pr) else (np.nan, np.nan)
same = coh[(coh.price_rose == False)]
res["price_rose"] = dict(users=len(pr), churn=pr_c, ci=[lo, hi], churn_not_rose=same.is_churn.mean(),
                         by_new_price=pr.groupby("price").is_churn.agg(["size", "mean"]).to_dict(),
                         exceeds_break_even=bool(pr_c > c_be))
md += ["", "## 4. What would change my mind: users whose price went up", "",
       f"- {len(pr):,} users; churn {pr_c:.2%} (95% CI {lo:.2%}–{hi:.2%}) vs {same.is_churn.mean():.2%} for users whose price did not rise.",
       f"- Above the break-even churn of {c_be:.2%}? **{'Yes, this changes my mind' if pr_c > c_be else 'No'}**"]

# 5. secondary: same price, different payment methods (why pm41 only)
pm = rate_table(base[base.price == 149], "pm")
pm = pm[pm.users >= 1000].sort_values("churn")
pm.to_csv(f"{OUT}/pm149_table.csv")
md += ["", "## 5. Same price (149), different payment methods (methods with ≥ 1,000 users)", "",
       "| pm | users | churn | 95% CI |", "|---|---|---|---|"]
md += [f"| {p} | {r.users:,} | {r.churn:.2%} | {r.churn_lo:.2%}–{r.churn_hi:.2%} |" for p, r in pm.iterrows()]

# 6. engagement (concurrent with the renewal window: descriptive, not a predictor)
e = coh.copy()
e["listen_band"] = pd.cut(e.listen_days_march.fillna(0), [-1, 0, 7, 15, 23, 31],
                          labels=["no logs", "1-7 d", "8-15 d", "16-23 d", "24-31 d"])
eg = rate_table(e, "listen_band")
eg.to_csv(f"{OUT}/listening_table.csv")
md += ["", "## 6. Listening days in March vs churn (concurrent, descriptive only)", "",
       "| days listened | users | churn |", "|---|---|---|"]
md += [f"| {b} | {r.users:,} | {r.churn:.2%} |" for b, r in eg.iterrows()]

# 7. test size: detect a 0.5-point churn rise on 149 at 80% power, alpha 0.05
es = proportion_effectsize(c149 + 0.005, c149)
n_arm = NormalIndPower().solve_power(es, power=0.8, alpha=0.05)
res["test"] = dict(base=c149, mde_pts=0.5, n_per_arm=int(np.ceil(n_arm)))
md += ["", "## 7. Price test size", "",
       f"- To detect churn moving from {c149:.2%} to {c149 + 0.005:.2%} (80% power, α = 0.05): **{int(np.ceil(n_arm)):,} users per arm**."]

json.dump(res, open(f"{OUT}/results.json", "w"), indent=2, default=float)
open(f"{OUT}/results.md", "w").write("\n".join(md) + "\n")
print("\n".join(md))
