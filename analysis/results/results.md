# Pricing analysis (Phase 2)

## 1. Cohort (pm41, 30-day auto-renew, expiring in March): churn and 12-month revenue by tier

Cohort size: 531,743 users (step 7 of the funnel).

| price | users | churn | 95% CI | cancel | downgrade | R (12 m, TWD) |
|---|---|---|---|---|---|---|
| 99.0 | 360,805.0 | 1.81% | 1.77%–1.86% | 2.20% | 0.01% | 1,076 |
| 100.0 | 24,761.0 | 0.62% | 0.53%–0.72% | 0.39% | 0.08% | 1,160 |
| 129.0 | 28,901.0 | 2.96% | 2.77%–3.16% | 3.76% | 2.09% | 1,319 |
| 149.0 | 117,276.0 | 3.43% | 3.33%–3.54% | 5.19% | 2.66% | 1,486 |

## 2. The decision rule

- R(99) = 1,076, R(149) = 1,486, gap = 410 TWD (bootstrap 95% CI 401 to 418).
- Break-even churn for 149 = 9.86%; observed 149 churn = 3.43%; margin = 6.4 points.
- **Verdict: 1. 149 pays: propose a price test that moves new subscribers to 149.**

## 3. Confounder check: tenure

| tenure | price | users | churn |
|---|---|---|---|
| 1-2y | 99.0 | 170,722.0 | 1.83% |
| 1-2y | 149.0 | 25,060.0 | 2.85% |
| <1y | 99.0 | 144,689.0 | 1.92% |
| <1y | 149.0 | 17,381.0 | 4.05% |
| >2y | 99.0 | 45,394.0 | 1.42% |
| >2y | 149.0 | 74,835.0 | 3.49% |

- Crude churn gap 149 − 99 = 1.62 pts; tenure-standardised gap = 1.66 pts (shrinks -2%).
- Odds ratio crude 1.92 → Mantel-Haenszel 2.07 (95% CI 1.97–2.17).
- Rule: tenure explains most of the gap? **No**

## 4. What would change my mind: users whose price went up

- 2,469 users; churn 2.07% (95% CI 1.57%–2.71%) vs 2.21% for users whose price did not rise.
- Above the break-even churn of 9.86%? **No**

## 5. Same price (149), different payment methods (methods with ≥ 1,000 users)

| pm | users | churn | 95% CI |
|---|---|---|---|
| 31.0 | 9,660.0 | 0.92% | 0.75%–1.13% |
| 34.0 | 27,813.0 | 0.95% | 0.85%–1.07% |
| 23.0 | 1,617.0 | 1.67% | 1.15%–2.42% |
| 37.0 | 33,974.0 | 2.54% | 2.38%–2.71% |
| 33.0 | 12,675.0 | 2.60% | 2.34%–2.90% |
| 27.0 | 1,664.0 | 2.88% | 2.18%–3.80% |
| 41.0 | 117,276.0 | 3.43% | 3.33%–3.54% |
| 40.0 | 70,146.0 | 5.84% | 5.67%–6.02% |
| 30.0 | 6,914.0 | 13.83% | 13.03%–14.66% |
| 39.0 | 2,116.0 | 53.92% | 51.79%–56.04% |

## 6. Listening days in March vs churn (concurrent, descriptive only)

| days listened | users | churn |
|---|---|---|
| no logs | 171,850.0 | 3.30% |
| 1-7 d | 91,542.0 | 3.06% |
| 8-15 d | 77,874.0 | 1.83% |
| 16-23 d | 77,729.0 | 1.13% |
| 24-31 d | 112,748.0 | 0.72% |

## 7. Price test size

- To detect churn moving from 3.43% to 3.93% (80% power, α = 0.05): **22,254 users per arm**.
