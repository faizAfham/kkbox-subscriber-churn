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


# ---------------------------------------------------------------- the memo
TIER_ROWS = "".join(
    f"<tr><td>{p}</td><td>{n0(t['users'])}</td><td>{pct(t['churn'], 2)} <span class='ci'>({pct(t['churn_lo'], 2)}–{pct(t['churn_hi'], 2)})</span></td>"
    f"<td>{pct(t['cancel'], 2)}</td><td>{pct(t['downgrade'], 2)}</td><td><b>{n0(t['R_12m'])}</b></td></tr>"
    for p, t in sorted(tier.items()))
FUNNEL = [("Users with the official churn label", "970,960", "starting point"),
          ("Has a subscription to price (valid payment on or before 28 Feb)", "968,436", "nothing to price otherwise"),
          ("30-day plan", "942,176", "long plans are a different product"),
          ("Auto-renew on", "853,899", "the decision is about automatic renewals"),
          ("Price is 99, 100, 129, 149 or 180", "853,555", "the tiers being compared"),
          ("Payment method 41", "543,671", "the only method that carries every tier"),
          ("Subscription expires in March 2017", f"{coh_n:,}", "the month the label covers")]
FUNNEL_ROWS = "".join(f"<tr><td>{i}</td><td>{a}</td><td>{b}</td><td>{c}</td></tr>" for i, (a, b, c) in enumerate(FUNNEL))
SENS_ROWS = "".join(
    f"<tr><td>{s['price_basis']}</td><td>{pct(s['churn149'], 2)}</td><td>{n0(s['R149'])}</td><td>{n0(s['gap'])}</td>"
    f"<td>{f(s['margin_pts']):.1f}</td><td>{'yes' if s['still_pays'] == 'True' else 'no'}</td></tr>" for s in sens)

ex1 = hbars([(f"TWD {p}", f(t["churn"]), f(t["churn_lo"]), f(t["churn_hi"]), SIENNA if p == 149 else BLUE)
             for p, t in sorted(tier.items())], fmt=lambda v: pct(v, 2))
ex4 = hbars([(f"method {int(float(r['pm']))}", f(r["churn"]), f(r["churn_lo"]), f(r["churn_hi"]),
              SIENNA if int(float(r["pm"])) == 39 else BLUE) for r in pm], label_w=90)
ex5 = hbars([(r["listen_band"].replace("no logs", "no listening logs"), f(r["churn"]), f(r["churn_lo"]), f(r["churn_hi"]), BLUE)
             for r in listen], label_w=130, fmt=lambda v: pct(v, 2))

HTML = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Pricing memo: 149 vs 99</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,600;1,8..60,400&display=swap" rel="stylesheet">
<style>
@page {{ size: A4; margin: 25mm 25mm 22mm;
  @bottom-left {{ content: "Pricing memo · KKBox subscriptions, March 2017"; font: 8pt Inter, sans-serif; color: {MUTED}; }}
  @bottom-right {{ content: "Page " counter(page) " of " counter(pages); font: 8pt Inter, sans-serif; color: {MUTED}; }} }}
html {{ background: #fff; }}
body {{ font: 10.5pt/1.5 "Source Serif 4", Georgia, serif; color: {INK}; max-width: 160mm; margin: 0 auto; }}
h1, h2, h3, .kicker, table, .src, .tldr .nums {{ font-family: Inter, sans-serif; }}
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
table {{ border-collapse: collapse; width: 100%; font-size: 8.5pt; margin: 4pt 0 2pt; font-variant-numeric: tabular-nums; break-inside: avoid; }}
th {{ text-align: left; font-weight: 600; border-bottom: 1pt solid {INK}; padding: 3pt 5pt; }}
td {{ border-bottom: 0.5pt solid #E3E6EA; padding: 3pt 5pt; }}
.ci {{ color: {MUTED}; font-size: 7.5pt; }}
.rule {{ border: 0.5pt solid #D5DAE3; padding: 8pt 11pt; margin: 6pt 0 10pt; font-size: 10pt; }}
.pb {{ break-before: page; }}
</style></head><body>

<div class="kicker">Analysis memo · Mohammad Faiz Ahmad · November 2026 · Data: KKBox (WSDM Cup 2018), {coh_n:,} subscribers</div>
<h1>Keep monthly subscribers on 149, and test it on new sign-ups: it earns TWD {rule['gap']:,.0f} more a year than 99, and churn would have to almost triple to erase that</h1>

<div class="tldr">
<p><b>Question.</b> Monthly subscribers paying TWD 149 churn more than those paying 99. Does the higher price still earn more per subscriber over a year?</p>
<p><b>Answer.</b> Yes, by a wide margin. Among {coh_n:,} comparable subscribers, 149 churns {pct(rule['c149'], 2)} a month against {pct(rule['c99'], 2)} for 99, but earns TWD {rule['R149']:,.0f} a year against {rule['R99']:,.0f}. Churn at 149 would have to reach {pct(rule['break_even_churn'], 2)} before 99 earns more.</p>
<p><b>Recommendation.</b> This comparison is observational, so it can't tell us how <i>new</i> users react to 149. Run a price test on new monthly sign-ups: about {test['n_per_arm']:,} users per arm over three billing cycles, with cancellations, downgrades and sign-up conversion as guardrails.</p>
<div class="nums">
<div><b>+TWD {rule['gap']:,.0f}</b><span>12-month revenue per subscriber, 149 vs 99 (95% CI {rule['gap_ci'][0]:,.0f}–{rule['gap_ci'][1]:,.0f})</span></div>
<div><b>{pct(rule['break_even_churn'], 2)}</b><span>monthly churn at which 149 stops paying (today {pct(rule['c149'], 2)})</span></div>
<div><b>{test['n_per_arm']:,}</b><span>users per arm to detect a 0.5-point churn rise</span></div>
</div></div>

<h2>1. Context</h2>
<p>Every subscription business that raises a price faces the same trade: more revenue from each person who stays, against more people who leave. A pricing team needs one number that weighs the two, and a threshold for when the trade stops paying. This memo produces both for KKBox, a Taiwanese music-streaming service that released real, anonymised subscriber data for the WSDM Cup 2018 churn challenge.</p>
<p>KKBox sells monthly plans at TWD 99, 100, 129, 149 and 180. In March 2017 the label tells us which subscribers did not renew within 30 days of their plan expiring. That is the definition of churn used throughout.</p>

<h2>2. Goals and non-goals</h2>
<p><b>Goals.</b> Estimate how churn differs by price for comparable subscribers; turn that into 12-month revenue per subscriber; decide, with a rule set in advance, whether 149 pays; and design the test that would confirm it.</p>
<p><b>Non-goals.</b> Predicting which individual will churn (a modelling problem, not a pricing decision); setting the optimal price (this data has five prices, not a demand curve); and anything about the 180 tier, which is sold through different payment methods and can't be compared fairly (section 6).</p>

<h2>3. Who is counted</h2>
<p>Each filter below is a judgment call that changes the answer, so each one is listed with its reason. The price of a subscriber is the list price of the plan that expires in March, taken from their last payment on or before 28 February. I didn't use the March payment, because that payment is often the renewal itself: anyone who has one is, by construction, not a churner, so pricing by it would leak the outcome.</p>
<figure><figcaption><span class="ex">Exhibit 1.</span> From 970,960 labelled users to a cohort of {coh_n:,} comparable monthly subscribers</figcaption>
<table><tr><th>#</th><th>Rule</th><th>Users left</th><th>Why</th></tr>{FUNNEL_ROWS}</table>
<div class="src">Source: KKBox train_v2, transactions, transactions_v2 (Kaggle). Ledger of 22,975,416 payments after removing 3,339 exact duplicates. Seven automated data checks pass.</div></figure>

<h2>4. How it is measured, and the rule written before the results</h2>
<ul>
<li><b>Churn rate</b> = subscribers with <code>is_churn = 1</code> ÷ subscribers in the tier. Unit: a person, not a payment.</li>
<li><b>12-month revenue per starting subscriber</b> = p × (1 − (1 − c)<sup>12</sup>) ÷ c, where p is the monthly price and c the monthly churn rate. It is the sum of 12 monthly payments, each a little less likely than the last. It assumes churn stays constant.</li>
<li><b>Break-even churn</b> = the churn rate at which 149's revenue equals 99's revenue today.</li>
<li><b>Guardrails</b>: March cancellation rate, and the share who renewed at a lower price (downgrades).</li>
</ul>
<div class="rule"><b>Decision rule (committed to git on 20 Nov 2026, before any churn rate was computed).</b> If 149 earns more than 99, the 95% interval of the gap is above zero, and 149's churn is at least 1 point below break-even: propose a price test that moves new subscribers to 149. If the interval includes zero or the margin is under 1 point: too close to call, so run the test first. If 149 earns less: don't raise the price.</div>

<h2>5. Findings</h2>
<h3>149 churns about twice as often as 99, but the gap is less than 2 points</h3>
<figure><figcaption><span class="ex">Exhibit 2.</span> Monthly churn by price, payment method 41 only (bars = rate, lines = 95% Wilson interval)</figcaption>
{ex1}
<table><tr><th>Price (TWD)</th><th>Users</th><th>Churn (95% CI)</th><th>Cancelled</th><th>Downgraded</th><th>Revenue, 12 m</th></tr>{TIER_ROWS}</table>
<div class="src">Source: kkbox-pricing-analysis notebook, results/tier_table.csv.</div></figure>
<p>Two things stand out. First, the 100 tier churns least of all ({pct(tier[100]['churn'], 2)}). An earlier pass on a truncated copy of the data, using cancellations as a stand-in for churn, had suggested the opposite; with the full data and the real label, that finding reversed. Second, the guardrails move with churn: at 149, {pct(tier[149]['cancel'], 1)} cancelled and {pct(tier[149]['downgrade'], 1)} downgraded, against {pct(tier[99]['cancel'], 1)} and {pct(tier[99]['downgrade'], 2)} at 99. A real price rise would need to watch both.</p>

<h3>Price still wins: 149 would need {pct(rule['break_even_churn'], 2)} churn before 99 earns more</h3>
<figure><figcaption><span class="ex">Exhibit 3.</span> 12-month revenue per subscriber at 149 falls as churn rises, but stays above 99 until churn reaches {pct(rule['break_even_churn'], 2)}</figcaption>
{breakeven_chart()}
<div class="src">Revenue = p × (1 − (1 − c)<sup>12</sup>) ÷ c. Bootstrap (10,000 draws) 95% CI of the gap: TWD {rule['gap_ci'][0]:,.0f}–{rule['gap_ci'][1]:,.0f}.</div></figure>
<p>Under the committed rule the verdict is outcome 1: <b>149 pays</b>. The gap is TWD {rule['gap']:,.0f} per subscriber per year, its interval is nowhere near zero, and the margin to break-even is {rule['margin_pts']:.1f} points against the 1 point the rule asks for.</p>

<h2>6. Is it really the price?</h2>
<h3>Payment method had to be held fixed first</h3>
<p>Price is tangled up with how people pay. The 180 tier is sold only through methods that never carry 99, so a 180-vs-99 comparison would mostly compare payment channels. Payment method 41 is the only one that carries every tier from 99 to 149, which is why the cohort is limited to it. Exhibit 4 shows how much the method alone matters: at the same 149 price, churn runs from {pct(pm[0]['churn'])} to {pct(pm[-1]['churn'])}.</p>
<figure><figcaption><span class="ex">Exhibit 4.</span> Same price, very different churn: monthly churn at TWD 149 by payment method (methods with at least 1,000 users)</figcaption>
{ex4}<div class="src">All payment methods, 30-day auto-renew plans expiring in March 2017. Source: results/pm149_table.csv.</div></figure>

<h3>Tenure doesn't explain the gap</h3>
<p>Longer-standing subscribers churn less, and 149 users are more often long-standing, so tenure could have been hiding behind price. It isn't. Within tenure bands the gap is {ten['adjusted_gap_pts']:.2f} points against {ten['crude_gap_pts']:.2f} overall, and the Mantel-Haenszel odds ratio pooled across bands is {ten['mh_or']:.2f} (95% CI {ten['mh_or_ci'][0]:.2f}–{ten['mh_or_ci'][1]:.2f}). The gap is no smaller in any band.</p>
<figure><figcaption><span class="ex">Exhibit 5.</span> Within every tenure band, 149 (blue) churns more than 99 (green)</figcaption>
{grouped_tenure()}<div class="src">Tenure = days from first recorded payment (from Jan 2015) to the expiring payment.</div></figure>

<h3>People whose price went up don't change the verdict</h3>
<p>The rule named one result that would change my mind: users whose price rose churning above break-even. {rose['users']:,} users had a higher price on their expiring plan than on their previous one. Most of these moved from 99 to 100, so the useful group is the {rose149[0]:,} who moved up to 149. They churn at {pct(rose149[1])}, above 149's average of {pct(rule['c149'], 2)} (a price-shock effect), but far below the {pct(rule['break_even_churn'], 2)} break-even.</p>

<h2>7. How sure is the verdict?</h2>
<p>I stressed the two inputs most likely to be wrong: churn at 149, and the price itself (list price versus what people actually paid).</p>
<figure><figcaption><span class="ex">Exhibit 6.</span> The verdict survives 3 extra points of churn at 149 and the switch to the amount actually paid</figcaption>
<table><tr><th>Price basis</th><th>Churn at 149</th><th>Revenue at 149</th><th>Gap vs 99</th><th>Margin to break-even (pts)</th><th>Still pays?</th></tr>{SENS_ROWS}</table>
<div class="src">99's revenue held at TWD {rule['R99']:,.0f}. Source: results/sensitivity.csv.</div></figure>

<h2>8. Recommendation and the test</h2>
<p><b>Keep existing monthly subscribers on 149, and test 149 against 99 for new monthly sign-ups.</b> The existing-user data says 149 pays, but these users chose their price, so the data can't show how a new user facing 149 instead of 99 would behave, or whether they would sign up at all. A test answers that.</p>
<ul>
<li><b>Who:</b> new monthly sign-ups on payment method 41, randomly assigned at the offer screen to 99 or 149.</li>
<li><b>Primary metric:</b> revenue per assigned user over three billing cycles. Everyone assigned counts, including those who never convert.</li>
<li><b>Guardrails:</b> sign-up conversion, churn at each renewal, cancellations, downgrades, support contacts.</li>
<li><b>Size:</b> {test['n_per_arm']:,} users per arm to detect churn moving from {pct(test['base'], 2)} to {pct(test['base'] + 0.005, 2)} at 80% power, α = 0.05.</li>
<li><b>Duration:</b> at least three billing cycles, because the first renewal after a price change is when the price-shock effect shows up.</li>
<li><b>Ship rule, set now:</b> ship 149 if revenue per assigned user is higher with a 95% interval above zero and no guardrail worsens by more than 1 point.</li>
</ul>

<h2>9. A side finding worth a call: payment method 39</h2>
<p>At 149, subscribers paying through method 39 churn at {pct(p39['churn'])}, against {pct(p_other['churn'])} on other methods. It doesn't look like a promotion ending: they are long-standing (median tenure {p39['tenure_median_days']:,.0f} days), they paid full price, and their volume was steady through February. What stands out is that they rarely cancel ({pct(p39['cancelled_in_march'])} against {pct(p_other['cancelled_in_march'])}), and of the {renew39:,} who did renew, {switched39:,} ({switched39 / renew39:.0%}) switched to a different payment method. People who leave without cancelling, while those who stay change how they pay, is the pattern of <b>involuntary churn</b>: failed charges, or a method being withdrawn. KKBox doesn't document what method 39 is, so this is a question for the payments team, not a conclusion. If it is a billing failure, the roughly {round(p39['users'] * p39['churn']):,} who churned would have been worth about TWD {round(p39['users'] * p39['churn']) * rule['R149']:,.0f} a year at 149's revenue per subscriber.</p>

<h2>10. Risks, limits, and what would change my mind</h2>
<ul>
<li><b>Observational data.</b> Users picked their tier. The test in section 8 is the fix.</li>
<li><b>One renewal month.</b> The constant-churn assumption turns one month into a year. If churn at 149 rises over time, the margin shrinks; section 7 shows how far it can rise.</li>
<li><b>Listening is concurrent, not predictive.</b> Churn falls from {pct(listen[0]['churn'], 2)} with no listening logs to {pct(listen[-1]['churn'], 2)} for those who listened 24–31 days in March, but that is measured in the renewal month itself, so it describes churners rather than predicting them.</li>
<li><b>Music, not video.</b> KKBox is a Taiwanese music service in 2017. The method transfers to a video service; the numbers don't.</li>
<li><b>Age and gender</b> are valid for only 12% of the cohort, so I didn't use them.</li>
<li><b>What would change my mind:</b> a test where sign-up conversion at 149 falls by more than the revenue gain, or churn at 149 rising toward {pct(rule['break_even_churn'], 1)} over later renewals.</li>
</ul>

<h2>Appendix: reproduce every number</h2>
<p>Pipeline and notebooks: <code>subscriber-movements/</code>. Data never leaves Kaggle. Run, in order, the notebooks <code>kkbox-to-parquet</code> → <code>kkbox-pricing-mart</code> → <code>kkbox-pricing-analysis</code> → <code>kkbox-pricing-extras</code>; download their outputs into <code>analysis/results/</code>; then run <code>python memo/build_memo.py</code>, which builds this document from those files. The decision rule is <code>analysis/decision_rule.md</code>, committed before the analysis.</p>
<p class="src">Data: KKBox Churn Prediction Challenge, WSDM Cup 2018, kaggle.com/c/kkbox-churn-prediction-challenge. Method references: Wilson score interval; Mantel-Haenszel pooled odds ratio; two-proportion power analysis (statsmodels).</p>
</body></html>"""

(HERE / "memo.html").write_text(HTML)
print("wrote", HERE / "memo.html")
chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
if "--pdf" in sys.argv:
    subprocess.run([chrome, "--headless", "--disable-gpu", "--no-pdf-header-footer", "--virtual-time-budget=15000",
                    f"--user-data-dir={tempfile.mkdtemp()}",  # a separate profile, so an open Chrome window doesn't block it
                    f"--print-to-pdf={HERE / 'memo.pdf'}", (HERE / "memo.html").as_uri()],
                   stderr=subprocess.DEVNULL)  # Chrome can exit 2 on a harmless allocator warning even after writing the PDF
    print("wrote", HERE / "memo.pdf")
