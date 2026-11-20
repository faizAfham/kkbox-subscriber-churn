# Pricing analysis: extras

## 1. Sensitivity of the verdict

Average actually paid on the expiring subscription: 99-tier 99.0, 149-tier 148.9 TWD.

| price basis | 149 churn | R(99) | R(149) | gap | break-even churn | margin (pts) | still 'pays'? |
|---|---|---|---|---|---|---|---|
| list price | 3.43% | 1,076 | 1,486 | 410 | 9.86% | 6.4 | yes |
| list price | 4.43% | 1,076 | 1,410 | 334 | 9.86% | 5.4 | yes |
| list price | 5.43% | 1,076 | 1,340 | 263 | 9.86% | 4.4 | yes |
| list price | 6.43% | 1,076 | 1,273 | 197 | 9.86% | 3.4 | yes |
| actually paid | 3.43% | 1,076 | 1,485 | 409 | 9.84% | 6.4 | yes |
| actually paid | 4.43% | 1,076 | 1,409 | 333 | 9.84% | 5.4 | yes |
| actually paid | 5.43% | 1,076 | 1,339 | 262 | 9.84% | 4.4 | yes |
| actually paid | 6.43% | 1,076 | 1,272 | 196 | 9.84% | 3.4 | yes |

## 2. Why does 149 via pm39 churn so much?

| | pm39 @149 | other methods @149 |
|---|---|---|
| users | 2,116 | 284,070 |
| churn | 53.9% | 3.8% |
| discounted | 0.0% | 0.8% |
| paid_mean | 149.0 | 148.0 |
| paid_zero | 0.0% | 0.6% |
| tenure_median_days | 734 | 731 |
| tenure_lt_1y | 20.0% | 14.5% |
| cancelled_in_march | 0.9% | 4.5% |
| has_prev_price | 100.0% | 98.7% |
| listen_logs | 78.0% | 83.1% |

- registered_via (top 3) pm39: {9.0: 0.597, 3.0: 0.26, 4.0: 0.106} vs others: {9.0: 0.429, 7.0: 0.413, 3.0: 0.122}
- first transaction month (top): {'2015-01': 1190, '2016-07': 100, '2016-01': 70, '2015-03': 57, '2016-02': 52, '2015-12': 46}
- first transaction was pm39: 79.0%; ever paid 0 before March: 5.8%
- pm39 transactions by month (last 8): {'2016-07': 1823, '2016-08': 1893, '2016-09': 1930, '2016-10': 1985, '2016-11': 2022, '2016-12': 2109, '2017-01': 2132, '2017-02': 2056}
- March renewers: 1,018; their payment methods: {39: 528, 36: 194, 32: 75, 37: 71, 29: 68}
- pm39 churn at other prices: {'size': {149.0: 2116}, 'mean': {149.0: 0.5392}}
