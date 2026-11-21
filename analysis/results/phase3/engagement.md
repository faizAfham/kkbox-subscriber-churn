# Engagement before the renewal date (Phase 3 D)

Source: user_logs.csv, 392,106,543 rows streamed; Jan–Feb 2017 kept for the 760,163 base users (30-day, auto-renew, paid, standard tier, expiring in March). 77.1% listened at least once in Jan–Feb.
All listening here happened before the 28 Feb cutoff, so it can be used to predict March churn.

## Days listened in February vs March churn

| Feb days | users | share | churn | via cancel | silent |
|---|---|---|---|---|---|
| 0 d | 197,354.0 | 26% | 3.71% | 3.29% | 0.42% |
| 1-7 d | 141,332.0 | 19% | 3.22% | 2.68% | 0.54% |
| 8-14 d | 119,764.0 | 16% | 2.76% | 2.14% | 0.62% |
| 15-21 d | 127,038.0 | 17% | 2.57% | 1.89% | 0.67% |
| 22-28 d | 174,675.0 | 23% | 2.37% | 1.63% | 0.74% |

Same, payment method 41 only (the pricing cohort):

| Feb days | users | churn |
|---|---|---|
| 0 d | 172,939.0 | 2.95% |
| 1-7 d | 104,053.0 | 2.10% |
| 8-14 d | 78,996.0 | 1.80% |
| 15-21 d | 78,249.0 | 1.74% |
| 22-28 d | 97,506.0 | 1.55% |

## Listening trend, January → February

| trend | users | share | churn | via cancel | silent |
|---|---|---|---|---|---|
| stopped in Feb | 23,020.0 | 3% | 4.17% | 3.73% | 0.44% |
| silent both months | 174,334.0 | 23% | 3.65% | 3.23% | 0.42% |
| started in Feb | 33,036.0 | 4% | 3.32% | 2.85% | 0.47% |
| fell > 50% | 114,773.0 | 15% | 3.12% | 2.50% | 0.62% |
| rose > 50% | 95,788.0 | 13% | 2.57% | 1.95% | 0.62% |
| steady (±50%) | 319,212.0 | 42% | 2.54% | 1.86% | 0.69% |

## Early-warning flag: ≤ 7 listening days in Feb, or listening stopped / fell by more than half

- Flags 52.0% of users; their churn 3.42% vs 2.49% for the rest (lift 1.2×).
- Catches 64% of users who later cancelled and 44% of users who left silently.
