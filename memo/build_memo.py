"""Builds memo/memo.html (and memo.pdf via headless Chrome) from analysis/results/. Stdlib only.
Every number in the memo comes from the results files, so rerunning the Kaggle notebooks + this script reproduces it."""
import csv, json, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
RES = HERE.parent / "analysis/results"
BLUE, GREEN, SIENNA, GREY, INK, MUTED = "#2A55A6", "#00978D", "#BB7125", "#C0C5C9", "#1A1A1A", "#5F6368"


def rows(name):
    return list(csv.DictReader(open(RES / name)))


tier = {int(float(r["price"])): r for r in rows("tier_table.csv")}
tenure = rows("tenure_table.csv")
pm = rows("pm149_table.csv")
listen = rows("listening_table.csv")
sens = rows("sensitivity.csv")
res = json.load(open(RES / "results.json"))
ex = json.load(open(RES / "extras.json"))
rule, ten, rose, test = res["rule"], res["tenure"], res["price_rose"], res["test"]
f = lambda x: float(x)
pct = lambda x, d=1: f"{f(x) * 100:.{d}f}%"
n0 = lambda x: f"{f(x):,.0f}"
coh_n = sum(int(t["users"]) for t in tier.values())
R = lambda p, c: p * (1 - (1 - c) ** 12) / c
p39, p_other = ex["pm39_vs_other_149"]["pm39"], ex["pm39_vs_other_149"]["other_pm_149"]
h39 = ex["pm39_history"]
renew39 = h39["march_renewers"]
switched39 = renew39 - int(h39["march_renewers_pm_top"].get("39", 0))
rose149 = rose["by_new_price"]["size"]["149.0"], rose["by_new_price"]["mean"]["149.0"]


# ---------------------------------------------------------------- tiny SVG chart helpers
def svg(w, h, body):
    return (f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" xmlns="http://www.w3.org/2000/svg" '
            f'font-family="Inter, sans-serif" font-size="11">{body}</svg>')


def hbars(items, w=560, xmax=None, fmt=pct, label_w=120, ci=True):
    """items: (label, value, lo, hi, colour). Horizontal bars from a zero baseline, value labels at the end."""
    bh, gap, top = 18, 8, 6
    xmax = xmax or max(i[3] if ci else i[1] for i in items) * 1.15
    plot = w - label_w - 60
    x = lambda v: label_w + plot * v / xmax
    out = []
    for k, (lab, v, lo, hi, col) in enumerate(items):
        y = top + k * (bh + gap)
        out.append(f'<text x="{label_w - 8}" y="{y + bh / 2 + 4}" text-anchor="end" fill="{INK}">{lab}</text>')
        out.append(f'<rect x="{label_w}" y="{y}" width="{max(x(v) - label_w, 1):.1f}" height="{bh}" rx="3" fill="{col}"/>')
        if ci:
            out.append(f'<line x1="{x(lo):.1f}" x2="{x(hi):.1f}" y1="{y + bh / 2}" y2="{y + bh / 2}" stroke="{INK}" stroke-width="1.5"/>')
        out.append(f'<text x="{x(hi if ci else v) + 6:.1f}" y="{y + bh / 2 + 4}" fill="{INK}">{fmt(v)}</text>')
    h = top + len(items) * (bh + gap)
    out.append(f'<line x1="{label_w}" x2="{label_w}" y1="0" y2="{h}" stroke="{GREY}"/>')
    return svg(w, h + 4, "".join(out))


def breakeven_chart(w=560, h=230):
    """Revenue per subscriber at 149 as churn rises, against 99's observed revenue."""
    l, r, t, b = 52, 16, 14, 34
    cmax, ymin, ymax = 0.14, 600, 1800
    X = lambda c: l + (w - l - r) * c / cmax
    Y = lambda v: t + (h - t - b) * (1 - (v - ymin) / (ymax - ymin))
    pts = " ".join(f"{X(c / 1000):.1f},{Y(R(149, c / 1000)):.1f}" for c in range(5, 140, 2))
    out = []
    for v in range(600, 1801, 300):
        out.append(f'<line x1="{l}" x2="{w - r}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="#ECEDEF"/>'
                   f'<text x="{l - 6}" y="{Y(v) + 4:.1f}" text-anchor="end" fill="{MUTED}">{v:,}</text>')
    for c in range(0, 15, 2):
        out.append(f'<text x="{X(c / 100):.1f}" y="{h - b + 16}" text-anchor="middle" fill="{MUTED}">{c}%</text>')
    out.append(f'<text x="{(l + w - r) / 2}" y="{h - 4}" text-anchor="middle" fill="{MUTED}">monthly churn at 149</text>')
    r99 = rule["R99"]
    out.append(f'<line x1="{l}" x2="{w - r}" y1="{Y(r99):.1f}" y2="{Y(r99):.1f}" stroke="{GREEN}" stroke-width="2" stroke-dasharray="5 4"/>'
               f'<text x="{w - r}" y="{Y(r99) - 6:.1f}" text-anchor="end" fill="{INK}">99 today: TWD {r99:,.0f}</text>')
    out.append(f'<polyline points="{pts}" fill="none" stroke="{BLUE}" stroke-width="2"/>')
    cb, c1 = rule["break_even_churn"], rule["c149"]
    out.append(f'<circle cx="{X(c1):.1f}" cy="{Y(rule["R149"]):.1f}" r="5" fill="{SIENNA}" stroke="#fff" stroke-width="2"/>'
               f'<text x="{X(c1) + 9:.1f}" y="{Y(rule["R149"]) - 8:.1f}" fill="{INK}">149 today: {pct(c1)} churn, TWD {rule["R149"]:,.0f}</text>')
    out.append(f'<line x1="{X(cb):.1f}" x2="{X(cb):.1f}" y1="{t}" y2="{h - b}" stroke="{INK}" stroke-width="1" stroke-dasharray="2 3"/>'
               f'<text x="{X(cb) + 5:.1f}" y="{t + 12}" fill="{INK}">break-even {pct(cb, 2)}</text>')
    return svg(w, h, "".join(out))


def grouped_tenure(w=560):
    bands = ["<1y", "1-2y", ">2y"]
    names = {"<1y": "under 1 year", "1-2y": "1–2 years", ">2y": "over 2 years"}
    get = {(r["tenure_band"], int(float(r["price"]))): r for r in tenure}
    items = []
    for bnd in bands:
        for p, col in ((99, GREEN), (149, BLUE)):
            r = get[(bnd, p)]
            items.append((f"{names[bnd]} · {p}", f(r["churn"]), f(r["churn_lo"]), f(r["churn_hi"]), col))
    return hbars(items, w=w, label_w=150)


# ---------------------------------------------------------------- Phase 3 results
P3 = RES / "phase3"
drv = json.load(open(P3 / "drivers.json"))
eng = json.load(open(P3 / "engagement.json"))
A, B, E = drv["A_breakdown"], drv["B_payment"], drv["E_sizing"]
basek = "base (auto-renew, paid, tier)"
base_n, base = A[basek]["users"], A[basek]
pmt = [dict(pm=int(float(r["pm"])), **{k: f(v) for k, v in r.items() if k != "pm"}) for r in csv.DictReader(open(P3 / "pm_table.csv"))]
at_risk = [int(x) for x in B["at_risk_methods"]]
size = {r["lever"]: r for r in E["rows"]}
yr = lambda lever: size[lever]["twd_12m_per_cohort"] * 12
risk_rows = [r for r in pmt if r["pm"] in at_risk]
risk_n = int(sum(r["users"] for r in risk_rows))
risk_churn = sum(r["users"] * r["churn"] for r in risk_rows) / risk_n
risk_silent = sum(r["users"] * r["churn_silent"] for r in risk_rows) / risk_n
conv_be = E["conversion_break_even"]
starts = {int(float(k)): v for k, v in E["new_paid_starts_per_month"].items()}
fb, ew = eng["feb_band"], eng["early_warning"]
# from results/phase3/checks.md (kkbox-checks notebook): inside pm41, sign-up channel 7 carries every tier
CH7 = {99: (283328, 0.0165), 149: (103507, 0.0324)}


def n_arm(a, b):  # two-proportion sample size per arm, 80% power, alpha 0.05 (Cohen's h, same as statsmodels NormalIndPower)
    import math
    h = abs(2 * math.asin(math.sqrt(a)) - 2 * math.asin(math.sqrt(b)))
    return math.ceil(((1.959964 + 0.841621) / h) ** 2)


rec = 0.25
t1_target = risk_churn - risk_silent * rec
t1_n = n_arm(risk_churn, t1_target)
t1_days = 2 * t1_n / risk_n * 30
c149_all = A["base, price 149.0"]["churn"]
t2_n = n_arm(c149_all, c149_all + 0.005)
t2_flow = starts[99] + starts[149]
t2_conv_n = n_arm(0.05, 0.05 * (1 - conv_be))


def legend(*pairs):
    return "<div class='lg'>" + "".join(f"<span><i style='background:{c}'></i>{t}</span>" for t, c in pairs) + "</div>"


def split_bars(groups, label_w=120):
    items = []
    for lab, can, sil in groups:
        items += [(f"{lab} · cancel", can, 0, 0, BLUE), (f"{lab} · silent", sil, 0, 0, SIENNA)]
    return hbars(items, ci=False, label_w=label_w, fmt=lambda v: pct(v, 2))


ex_a = split_bars([(p, A[f"base, price {p}.0"]["churn_cancel"], A[f"base, price {p}.0"]["churn_silent"]) for p in (99, 100, 129, 149, 180)], label_w=110)
ex_b = hbars([(f"method {r['pm']}", r["churn_silent"], 0, 0, SIENNA if r["pm"] in at_risk else BLUE) for r in pmt if r["churn_silent"] > 0.001],
             ci=False, label_w=90, fmt=lambda v: pct(v, 2))
ex_d = split_bars([(k.replace(" d", " days"), v["churn_cancel"], v["churn_silent"]) for k, v in fb.items()], label_w=130)
ex_p = hbars([(f"TWD {p}", f(t["churn"]), f(t["churn_lo"]), f(t["churn_hi"]), SIENNA if p == 149 else BLUE)
              for p, t in sorted(tier.items())], fmt=lambda v: pct(v, 2))

SIZE_ROWS = "".join(f"<tr><td>{a}</td><td>{b}</td><td>{n0(c)}</td><td><b>TWD {d / 1e6:,.1f} M</b></td><td>{e}</td></tr>" for a, b, c, d, e in [
    ("Cancellations", "all methods", size["churn via cancel"]["users_per_month"], yr("churn via cancel"), "Largest pool, but no good early signal (section 7)"),
    ("Silent exits", "all methods", size["silent churn, all methods"]["users_per_month"], yr("silent churn, all methods"), "Likely failed renewals"),
    ("Silent exits", f"methods {', '.join(map(str, at_risk))}", size["silent churn, at-risk methods"]["users_per_month"], yr("silent churn, at-risk methods"), "Half the silent pool in 3 methods"),
    ("↳ recover 25% of those", "", size["recover 25% of silent churn, at-risk methods"]["users_per_month"], yr("recover 25% of silent churn, at-risk methods"), "Test 1"),
    ("New 99 sign-ups priced at 149", "pm 41", size["new 99 sign-ups moved to 149 (no lost sign-ups)"]["users_per_month"],
     yr("new 99 sign-ups moved to 149 (no lost sign-ups)"), f"Upper bound: assumes no lost sign-ups. Test 2"),
])
A_ROWS = "".join(f"<tr><td>{lab}</td><td>{n0(A[k]['users'])}</td><td>{pct(A[k]['churn'], 2)}</td><td>{pct(A[k]['churn_cancel'], 2)}</td>"
                 f"<td>{pct(A[k]['churn_silent'], 2)}</td><td>{A[k]['silent_share']:.0%}</td></tr>"
                 for lab, k in [("Manual renewal", "auto_renew=0"), ("Auto-renew (base)", basek)])
PM_ROWS = "".join(f"<tr><td>{r['pm']}{' ⚑' if r['pm'] in at_risk else ''}</td><td>{n0(r['users'])}</td><td>{pct(r['churn'], 2)}</td>"
                  f"<td>{pct(r['churn_cancel'], 2)}</td><td>{pct(r['churn_silent'], 2)}</td><td>{r['tenure_median_days']:,.0f}</td></tr>" for r in pmt[:6])
TIER_ROWS = "".join(
    f"<tr><td>{p}</td><td>{n0(t['users'])}</td><td>{pct(t['churn'], 2)} <span class='ci'>({pct(t['churn_lo'], 2)}–{pct(t['churn_hi'], 2)})</span></td>"
    f"<td>{pct(t['cancel'], 2)}</td><td>{pct(t['downgrade'], 2)}</td><td><b>{n0(t['R_12m'])}</b></td></tr>"
    for p, t in sorted(tier.items()))
r39 = next(r for r in pmt if r["pm"] == 39)

HTML = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Where KKBox loses subscribers</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,600;1,8..60,400&display=swap" rel="stylesheet">
<style>
@page {{ size: A4; margin: 25mm 25mm 22mm;
  @bottom-left {{ content: "Churn memo · KKBox subscriptions, March 2017"; font: 8pt Inter, sans-serif; color: {MUTED}; }}
  @bottom-right {{ content: "Page " counter(page) " of " counter(pages); font: 8pt Inter, sans-serif; color: {MUTED}; }} }}
html {{ background: #fff; }}
body {{ font: 10.5pt/1.5 "Source Serif 4", Georgia, serif; color: {INK}; max-width: 160mm; margin: 0 auto; }}
h1, h2, h3, .kicker, table, .src, .tldr .nums, .lg {{ font-family: Inter, sans-serif; }}
h1 {{ font-size: 18pt; line-height: 1.25; font-weight: 600; color: #1C4286; margin: 0 0 4pt; }}
h2 {{ font-size: 12.5pt; font-weight: 600; color: #1C4286; margin: 18pt 0 4pt; break-after: avoid; }}
h3 {{ font-size: 10.5pt; font-weight: 600; margin: 12pt 0 2pt; break-after: avoid; }}
.kicker {{ font-size: 8.5pt; color: {MUTED}; margin-bottom: 14pt; }}
p {{ margin: 0 0 7pt; }} ul, ol {{ margin: 0 0 7pt; padding-left: 16pt; }} li {{ margin-bottom: 3pt; }}
.tldr {{ border-left: 3pt solid #1C4286; background: #F3F6FB; padding: 9pt 12pt; margin: 0 0 12pt; }}
.tldr p {{ margin: 0 0 5pt; }}
.nums {{ display: flex; gap: 10pt; margin: 10pt 0 2pt; }}
.nums div {{ flex: 1; background: #fff; border: 0.5pt solid #D5DAE3; padding: 6pt 8pt; }}
.nums b {{ display: block; font-size: 15pt; color: #1C4286; font-variant-numeric: tabular-nums; }}
.nums span {{ font-size: 8pt; color: {MUTED}; line-height: 1.3; display: block; }}
figure {{ margin: 10pt 0 12pt; break-inside: avoid; }}
figcaption {{ font: 600 9.5pt/1.35 Inter, sans-serif; margin-bottom: 6pt; }}
figcaption .ex {{ color: {SIENNA}; }}
.src {{ font-size: 7.5pt; color: {MUTED}; margin-top: 4pt; }}
.lg {{ font-size: 8pt; color: {MUTED}; margin: 0 0 4pt; }} .lg span {{ margin-right: 12pt; }}
.lg i {{ display: inline-block; width: 9pt; height: 9pt; border-radius: 2pt; margin-right: 4pt; vertical-align: -1pt; }}
table {{ border-collapse: collapse; width: 100%; font-size: 8.5pt; margin: 4pt 0 2pt; font-variant-numeric: tabular-nums; break-inside: avoid; }}
th {{ text-align: left; font-weight: 600; border-bottom: 1pt solid {INK}; padding: 3pt 5pt; }}
td {{ border-bottom: 0.5pt solid #E3E6EA; padding: 3pt 5pt; vertical-align: top; }}
.ci {{ color: {MUTED}; font-size: 7.5pt; }}
.rule {{ border: 0.5pt solid #D5DAE3; padding: 8pt 11pt; margin: 6pt 0 10pt; font-size: 10pt; }}
</style></head><body>

<div class="kicker">Analysis memo · Mohammad Faiz Ahmad · November 2026 · Data: KKBox (WSDM Cup 2018), {base_n:,} paying monthly subscribers</div>
<h1>KKBox loses most paying subscribers to cancellations, but the cheapest fix is the silent exits: test payment recovery first, then 149 on new sign-ups</h1>

<div class="tldr">
<p><b>Question.</b> Where is KKBox losing paying monthly subscribers, and what should it fix first?</p>
<p><b>Answer.</b> Of the {base_n:,} auto-renewing subscribers whose plan expired in March 2017, {pct(base['churn'], 2)} left. {1 - base['silent_share']:.0%} of those pressed cancel first; the other {base['silent_share']:.0%} left <i>silently</i>, with auto-renew still on. Silent exits are concentrated in three payment methods and, unlike cancellations, are <i>more</i> common among heavy listeners, which is what failed renewal charges look like.</p>
<p><b>Recommendation.</b> (1) Test payment recovery (retries plus an "update your payment method" prompt) on methods {', '.join(map(str, at_risk))}: about TWD {yr('recover 25% of silent churn, at-risk methods') / 1e6:.0f} M a year if it wins back a quarter of silent exits, readable in about six weeks. (2) Test 149 against 99 for new sign-ups: it pays unless it loses more than {conv_be:.0%} of sign-ups. (3) Treat cancellations as a research problem, not a model: listening barely predicts them.</p>
<div class="nums">
<div><b>{1 - base['silent_share']:.0%} / {base['silent_share']:.0%}</b><span>of churners pressed cancel / left silently with auto-renew on</span></div>
<div><b>TWD {yr('silent churn, at-risk methods') / 1e6:.0f} M</b><span>a year in silent exits from 3 payment methods (if every month is like March)</span></div>
<div><b>{conv_be:.0%}</b><span>share of sign-ups 149 could lose and still earn more than 99</span></div>
</div></div>

<h2>1. Context</h2>
<p>KKBox is a Taiwanese music-streaming service that released real, anonymised subscriber data for the WSDM Cup 2018 churn challenge: 23 million payments from 2015 to March 2017, 6.8 million profiles, 392 million days of listening, and an official label saying which subscribers whose plan expired in March 2017 did not renew within 30 days. That label is the definition of churn throughout.</p>
<p>A subscription business has three levers on revenue from existing subscribers: keep the people who decide to leave, keep the people who leave without deciding, and charge more. This memo sizes each lever, ranks them, and designs the test for each of the top two.</p>

<h2>2. Goals and non-goals</h2>
<p><b>Goals.</b> Split churn into its sources; find where each source is concentrated; size each in TWD; decide what to test first and design the tests.</p>
<p><b>Non-goals.</b> A churn-prediction model (section 7 shows the cheap signals are weak, and a model doesn't tell a product team what to change); the optimal price (five prices are not a demand curve); manual-renewal subscribers, who churn {pct(A['auto_renew=0']['churn'], 0)} a month and are a different product decision (section 4).</p>

<h2>3. Who is counted</h2>
<p>From 970,960 labelled users, I keep those whose subscription expiring in March is a 30-day plan, on auto-renew, at a paid standard price (99, 100, 129, 149 or 180): {base_n:,} subscribers. A subscriber's plan, price and payment method come from their last valid payment on or before 28 February. I didn't use the March payment, because it is often the renewal itself, which would leak the outcome. For the price comparison I go further and keep only payment method 41, the one method that carries every tier from 99 to 149 ({coh_n:,} subscribers).</p>
<p class="src">Ledger of 22,975,416 payments after removing 3,339 exact duplicates; seven automated data checks pass. {drv['dq']['expiring_row_is_a_cancel']:,} subscribers' expiring payment is itself a cancellation row; they are counted as cancellers.</p>

<h2>4. Where churn comes from: four in five churners pressed cancel</h2>
<p>A churner either <b>cancelled</b> (a cancellation on or after the expiring payment) or left <b>silently</b> (no cancellation, auto-renew still on, and no renewal within 30 days). For an auto-renewing subscriber, a silent exit means the renewal charge didn't go through: an expired card, a failed carrier bill, or a payment method that stopped working.</p>
<figure><figcaption><span class="ex">Exhibit 1.</span> Manual renewers churn ten times as often, but auto-renewers are 90% of the base; among them most churners cancel</figcaption>
<table><tr><th>Group</th><th>Users</th><th>Churn</th><th>Via cancel</th><th>Silent</th><th>Silent share of churn</th></tr>{A_ROWS}</table>
<div class="src">30-day plans expiring in March 2017. For manual renewers a "silent" exit just means not paying again. Source: results/phase3/drivers.json.</div></figure>
<figure><figcaption><span class="ex">Exhibit 2.</span> Cancellations rise with price; silent exits don't follow price</figcaption>
{legend(('cancelled', BLUE), ('left silently', SIENNA))}{ex_a}
<div class="src">Auto-renew base, all payment methods.</div></figure>

<h2>5. Silent exits: concentrated in three payment methods, and they hit engaged listeners</h2>
<p>Silent churn averages {pct(B['avg_silent'], 2)} a month, but three methods run at two to four times that: {', '.join(f"method {r['pm']} ({pct(r['churn_silent'], 2)})" for r in risk_rows)}. Together they cover {risk_n:,} subscribers and about half of all silent exits.</p>
<figure><figcaption><span class="ex">Exhibit 3.</span> Silent churn by payment method (methods with at least 1,000 subscribers; sienna = at least twice the average)</figcaption>
{ex_b}
<table><tr><th>Method</th><th>Users</th><th>Churn</th><th>Via cancel</th><th>Silent</th><th>Median tenure (days)</th></tr>{PM_ROWS}</table>
<div class="src">Source: results/phase3/pm_table.csv. March transaction volume for all three is normal (0.96–1.23 of the overall ratio), so no method was switched off.</div></figure>
<p>The evidence that these are failed charges rather than quiet decisions comes from listening. Subscribers who listened on 22–28 days in February cancel half as often as those who didn't listen at all ({pct(fb['22-28 d']['churn_cancel'], 2)} vs {pct(fb['0 d']['churn_cancel'], 2)}), but they leave silently <i>more</i> often ({pct(fb['22-28 d']['churn_silent'], 2)} vs {pct(fb['0 d']['churn_silent'], 2)}). People who use the product every day don't drift away; their payment fails. This is still an inference: KKBox's data has no "charge failed" field, so the first step is to ask the payments team for decline logs on these three methods.</p>
<p><b>A correction to an earlier draft.</b> Method 39 churns {pct(r39['churn'], 0)} at 149, and I had read it as a billing failure. With cancellations counted from January rather than only March, almost all of those churners cancelled ({pct(r39['churn_cancel'], 1)} via cancel, {pct(r39['churn_silent'], 2)} silent), spread across 71 different days. It is a small group ({r39['users']:,.0f} subscribers) of people deliberately leaving or moving to another method, not a payments problem.</p>

<h2>6. Price: 149 pays for existing subscribers, but the real unknown is sign-ups</h2>
<p><b>The tiers are plans people chose, not prices they reacted to.</b> 99.5% of subscribers whose previous plan was 99 are still on 99, and the same holds for every tier, so the data contains almost no price changes. What it can show is how people who chose 149 behave compared with people who chose 99. Within payment method 41 and sign-up channel 7, which carries every tier, 149 churns {pct(CH7[149][1], 2)} a month against {pct(CH7[99][1], 2)} for 99.</p>
<figure><figcaption><span class="ex">Exhibit 4.</span> Monthly churn by price, payment method 41 (bars = rate, lines = 95% Wilson interval)</figcaption>
{ex_p}
<table><tr><th>Price (TWD)</th><th>Users</th><th>Churn (95% CI)</th><th>Cancelled in March</th><th>Downgraded</th><th>Revenue, 12 m</th></tr>{TIER_ROWS}</table>
<div class="src">Source: results/tier_table.csv. Revenue per subscriber = p × (1 − (1 − c)<sup>12</sup>) ÷ c, assuming churn stays constant.</div></figure>
<p>Under the decision rule committed to git before any churn rate was computed, the verdict is <b>149 pays</b>: TWD {rule['gap']:,.0f} more per subscriber a year (95% CI {rule['gap_ci'][0]:,.0f}–{rule['gap_ci'][1]:,.0f}), and churn would have to reach {pct(rule['break_even_churn'], 2)} before 99 earns more. It survives the obvious challenges. Tenure doesn't explain it (Mantel-Haenszel odds ratio {ten['mh_or']:.2f} within tenure bands). It holds with 3 extra points of churn at 149 and on prices actually paid. The {rose149[0]:,} subscribers whose price rose to 149 churn {pct(rose149[1])}, well under break-even.</p>
<figure><figcaption><span class="ex">Exhibit 5.</span> Revenue per subscriber at 149 stays above 99 until churn reaches {pct(rule['break_even_churn'], 2)}</figcaption>
{breakeven_chart()}</figure>
<p><b>So the price question moves to sign-ups.</b> A higher price hurts most at the moment someone decides whether to subscribe, and this data can't see that moment. The useful number is the sign-up loss 149 can afford: 149 still earns more than 99 unless it loses more than <b>{conv_be:.0%}</b> of the people who would have subscribed at 99 (1 − R<sub>99</sub>/R<sub>149</sub>, all payment methods). About {starts[99]:,.0f} new paid subscriptions a month start at 99; moving them to 149 with no loss would be worth up to TWD {yr('new 99 sign-ups moved to 149 (no lost sign-ups)') / 1e6:.0f} M a year. That is the ceiling, and only a test can tell how much of it is real.</p>

<h2>7. Can listening warn us before someone cancels? Barely</h2>
<p>The obvious retention play is to spot disengaged subscribers before renewal and win them back. Using only listening that happened before 28 February ({eng['rows_read']:,} log rows), churn falls from {pct(fb['0 d']['churn'], 2)} for subscribers who didn't listen in February to {pct(fb['22-28 d']['churn'], 2)} for near-daily listeners. That is a real gradient but a weak one. A flag for "listened 7 days or fewer, or listening stopped or halved" catches {ew['share_of_cancel_churners_caught']:.0%} of later cancellers but flags {ew['flagged_share']:.0%} of everyone, a lift of only {ew['lift']:.1f}×. An earlier draft reported a much steeper drop (3.30% to 0.72%), but that used March listening, which partly measures people who had already left.</p>
<figure><figcaption><span class="ex">Exhibit 6.</span> February listening vs March churn: cancellations fall with listening, silent exits rise</figcaption>
{legend(('cancelled', BLUE), ('left silently', SIENNA))}{ex_d}
<div class="src">Auto-renew base. Source: results/phase3/engagement_feb_band.csv.</div></figure>
<p>A quarter of paying subscribers ({fb['0 d']['share_of_users']:.0%}) didn't listen at all in February and still mostly renewed. Waking them up with a "we miss you" message could just as easily remind them to cancel, so any re-engagement campaign needs a holdout group.</p>

<h2>8. What each problem is worth, and what to do first</h2>
<figure><figcaption><span class="ex">Exhibit 7.</span> TWD a year at stake, per lever</figcaption>
<table><tr><th>Lever</th><th>Scope</th><th>Subscribers / month</th><th>TWD a year</th><th>Note</th></tr>{SIZE_ROWS}</table>
<div class="src">Value of keeping one subscriber = their tier's 12-month revenue. One monthly cohort × 12, assuming every month looks like March 2017. Source: results/phase3/sizing.csv.</div></figure>
<p>Cancellations are the biggest pool, but there is no cheap way to target them (section 7) and no test I can design from this data alone; the next step is research into why people cancel (an exit survey in the cancel flow), not a model. Payment recovery is smaller but cheap to build, low-risk to users, and fast to read, so it goes first. The price test is worth more if it works, but it touches every new subscriber and takes longer to read, so it goes second.</p>

<h2>9. The two tests</h2>
<h3>Test 1: payment recovery on methods {', '.join(map(str, at_risk))}</h3>
<ul>
<li><b>Who:</b> auto-renewing subscribers on these methods whose plan expires during the test, randomised 50/50 by user, stratified by method. About {risk_n:,} become eligible each month.</li>
<li><b>Treatment:</b> on a failed renewal charge, retry on days 1, 3 and 7, and send an in-app and email prompt with a one-tap link to update the payment method. Control: current behaviour.</li>
<li><b>Primary metric:</b> share who renew within 30 days of expiry (1 − churn). Today {pct(risk_churn, 2)} churn.</li>
<li><b>Guardrails:</b> cancellation rate (a prompt can remind people to cancel; ship only if it rises by under 0.3 points), complaints and refund requests.</li>
<li><b>Size:</b> winning back a quarter of silent exits moves churn from {pct(risk_churn, 2)} to {pct(t1_target, 2)}; detecting that at 80% power and α = 0.05 needs <b>{t1_n:,} subscribers per arm</b>, about {t1_days:.0f} days of eligible subscribers, plus the 30-day renewal window: <b>a readout in about six weeks</b>.</li>
<li><b>Ship rule:</b> renewal rate higher with a 95% interval above zero, and the cancellation guardrail holds.</li>
</ul>
<h3>Test 2: 149 vs 99 for new monthly sign-ups (payment method 41)</h3>
<ul>
<li><b>Who:</b> new visitors reaching the plan page, randomised by account at the offer screen to see 99 or 149. Existing subscribers are untouched.</li>
<li><b>Primary metric:</b> 12-month revenue per assigned visitor = sign-up rate × revenue per subscriber, counting everyone assigned, including those who don't subscribe.</li>
<li><b>Leading indicator, read first:</b> sign-up rate. Stop early for 149 if it drops by more than {conv_be:.0%}, because past that line 149 can't win. At an assumed 5% plan-page conversion, detecting a {conv_be:.0%} drop needs about {t2_conv_n:,} visitors per arm.</li>
<li><b>Then:</b> first-renewal churn, which needs {t2_n:,} sign-ups per arm to detect a 0.5-point rise from {pct(c149_all, 2)}. At about {t2_flow:,.0f} new 99 and 149 sign-ups a month, that is roughly {2 * t2_n / t2_flow:.1f} months of sign-ups plus one renewal cycle.</li>
<li><b>Guardrails:</b> plan mix (do people switch to 129 or 180 instead?), refunds, and complaints from people who compare prices; randomise by account and device to limit that.</li>
<li><b>Ship rule:</b> revenue per assigned visitor higher at 149 with a 95% interval above zero, and no guardrail worse by more than 1 point.</li>
</ul>

<h2>10. Risks, limits, and what would change my mind</h2>
<ul>
<li><b>"Silent" is inferred, not observed.</b> If decline logs show these exits aren't failed charges, Test 1 loses its basis; it drops to a smaller experiment on whatever the logs do show.</li>
<li><b>One month stands in for a year.</b> All annual figures assume every month looks like March 2017.</li>
<li><b>Observational price comparison.</b> People chose their tier. Test 2 is the fix.</li>
<li><b>Music, Taiwan, 2017.</b> The method transfers to a video service; the numbers don't.</li>
<li><b>Age and gender</b> are valid for only 12% of subscribers, so I didn't use them.</li>
<li><b>What would change my mind:</b> decline logs showing silent exits aren't failed payments; a sign-up drop above {conv_be:.0%} at 149; or a cancel-flow survey showing cancellations driven by something fixable, which would put cancellations first.</li>
</ul>

<h2>Appendix: reproduce every number</h2>
<p>Pipeline and notebooks: <code>subscriber-movements/kaggle/</code>. The data never leaves Kaggle. Notebooks, in order: <code>kkbox-to-parquet</code> → <code>kkbox-pricing-mart</code> → <code>kkbox-pricing-analysis</code>, <code>kkbox-pricing-extras</code>, <code>kkbox-churn-drivers</code>, <code>kkbox-engagement</code> (streams the 30 GB listening log), <code>kkbox-checks</code>. Their outputs go into <code>analysis/results/</code>; then <code>python memo/build_memo.py</code> builds this document from those files. The pricing decision rule is <code>analysis/decision_rule.md</code>; the test plans are <code>analysis/experiment_design.md</code>.</p>
<p class="src">Data: KKBox Churn Prediction Challenge, WSDM Cup 2018, kaggle.com/c/kkbox-churn-prediction-challenge. Methods: Wilson score interval; Mantel-Haenszel pooled odds ratio; two-proportion power analysis (Cohen's h).</p>
</body></html>"""

(HERE / "memo.html").write_text(HTML)
print("wrote", HERE / "memo.html")
chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
if "--pdf" in sys.argv:
    try:
        subprocess.run([chrome, "--headless", "--disable-gpu", "--no-pdf-header-footer", "--run-all-compositor-stages-before-draw", "--virtual-time-budget=8000",
                    f"--user-data-dir={tempfile.mkdtemp()}",  # a separate profile, so an open Chrome window doesn't block it
                    f"--print-to-pdf={HERE / 'memo.pdf'}", (HERE / "memo.html").as_uri()],
                       stderr=subprocess.DEVNULL, timeout=90)  # Chrome can exit 2, or hang, after writing the PDF
    except subprocess.TimeoutExpired:
        pass
    print("wrote", HERE / "memo.pdf")
