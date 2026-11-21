# Experiment designs (Phase 3 F)

Two tests, in priority order. Sizes come from `results/phase3/` (drivers.json, experiment_sizes.csv) and the memo builder's `n_arm()`:
two-proportion test, 80% power, α = 0.05 two-sided, Cohen's h.

## Before either test: check the assumption

"Silent" churn (auto-renew on, no cancel, no renewal within 30 days) is inferred, not observed. Ask the payments team for
renewal-charge decline logs on methods 40, 30 and 29 for one month. If most silent exits there have a declined charge,
run Test 1. If not, Test 1 shrinks to whatever the logs show.

## Test 1: payment recovery (run first)

| | |
|---|---|
| Hypothesis | Silent exits on methods 40/30/29 are mostly failed renewal charges; retrying and prompting a payment update wins back a share of them. |
| Unit / randomisation | User, 50/50, hash of user id, stratified by payment method. Assigned when their plan enters the last 7 days before expiry. |
| Eligible | Auto-renewing 30-day subscribers on methods 40, 30 or 29: ~92,479 expiring per month. |
| Treatment | On a failed charge: retry on days 1, 3, 7, plus an in-app and email prompt with a one-tap "update payment method" link. Control: current behaviour. |
| Primary metric | Renewed within 30 days of expiry (= 1 − KKBox churn). Baseline churn 6.69%. |
| Secondary | Silent-churn rate; recovered revenue (TWD); share who switch payment method. |
| Guardrails | Cancellation rate (non-inferiority margin: +0.3 pts); complaints; refund requests. |
| Size | Win back 25% of silent exits → churn 6.69% → 6.10%: **13,624 per arm**, ~9 days of eligible users. Win back 50% → 5.52%: 3,255 per arm. |
| Duration | ~2 weeks of enrolment + 30-day renewal window → readout in **~6 weeks**. |
| Ship rule | Renewal rate higher, 95% CI of the difference above zero, cancellation guardrail within margin. |
| Value | 25% recovery ≈ TWD 9.3 M a year (×12 of one March-like cohort). |
| Risks | Prompts remind some people to cancel (guardrail); retries can trigger bank fraud flags (cap at 3); effect differs by method (report per stratum, but decide on the pooled result). |

## Test 2: 149 vs 99 for new monthly sign-ups (run second)

| | |
|---|---|
| Hypothesis | 149 earns more per visitor than 99 unless it cuts sign-ups by more than 25% (1 − R99/R149 = 1 − 1,076/1,429). |
| Unit / randomisation | Account (and device, to limit people comparing prices), 50/50 at the plan-offer screen. Existing subscribers are untouched. |
| Eligible | New visitors reaching the monthly-plan page on payment method 41. Today ~9,800 new paid sign-ups/month start at 99 and ~11,000 at 149. |
| Primary metric | 12-month revenue per assigned visitor = sign-up rate × revenue per subscriber, intention-to-treat (non-subscribers count as 0). |
| Leading indicator | Sign-up rate. At an assumed 5% plan-page conversion, detecting a 25% relative drop needs ~2,100 visitors per arm. Early stop for 149 if the drop exceeds 25% with its CI. |
| Follow-on | First-renewal churn: 26,545 sign-ups per arm to detect 4.18% → 4.68%, ~2.6 months of sign-ups + one renewal cycle. |
| Guardrails | Plan mix (switching to 129/180 or to annual plans); refunds; complaints. |
| Ship rule | Revenue per assigned visitor higher at 149, 95% CI above zero, no guardrail worse by > 1 pt. |
| Value ceiling | Up to TWD 41.5 M a year if no sign-ups are lost (the ceiling, not the forecast). |
| Risks | Price-discrimination complaints if users compare (randomise by account and device; consider rolling out by region instead); novelty (read renewals, not just week 1); the 5% conversion baseline is an assumption, replace it with the real funnel number. |

## Not tested (and why)

- **Cancellations** (TWD 288 M a year, the biggest pool): pre-renewal listening flags 52% of users to catch 64% of cancellers (1.2× lift), too weak to target. Next step is research, not a test: a one-question exit survey in the cancel flow for one month.
- **Re-engaging the 26% who didn't listen in February**: they mostly renew; a reminder may prompt cancels. Only with a holdout, and only after the survey says what to say.
