# Churn drivers (Phase 3)

## A. Churn breakdown: pressed cancel vs left without cancelling

30-day plans expiring in March 2017. 'Silent' = churned with no cancel on or after the expiring subscription.
For auto-renew users a silent exit means the renewal charge did not go through (or the method stopped working);
for manual-renew users it just means they did not pay again.

| group | users | churn | via cancel | silent | silent share of churn |
|---|---|---|---|---|---|
| auto_renew=0 | 83,200 | 27.11% | 0.06% | 27.05% | 100% |
| auto_renew=1 | 760,475 | 2.97% | 2.38% | 0.59% | 20% |
| base (auto-renew, paid, tier) | 760,163 | 2.97% | 2.38% | 0.59% | 20% |
| base, price 99.0 | 360,805 | 1.81% | 1.71% | 0.11% | 6% |
| base, price 100.0 | 27,223 | 0.76% | 0.58% | 0.19% | 25% |
| base, price 129.0 | 33,868 | 3.88% | 2.05% | 1.82% | 47% |
| base, price 149.0 | 286,186 | 4.18% | 3.13% | 1.05% | 25% |
| base, price 180.0 | 52,081 | 4.93% | 4.10% | 0.83% | 17% |

DQ: 3,406 of 760,163 base users have a cancel row as their expiring subscription.

## B. Silent churn by payment method (base, methods with ≥ 1,000 users)

Average silent churn: 0.59%. 'At risk' = silent churn ≥ 2× average: [40.0, 30.0, 29.0].
March volume index: the method's March/Feb transaction ratio divided by the ratio for all methods (1.0 = normal; near 0 = the method stopped being used).

| pm | users | churn | via cancel | silent | × avg | renewers who switched method | March volume index | median tenure (d) |
|---|---|---|---|---|---|---|---|---|
| 40.0 | 70,146 | 5.84% | 3.36% | 2.48% | 4.2 | 1% | 0.96 | 751 |
| 30.0 | 14,336 | 10.25% | 8.22% | 2.03% | 3.4 | 0% | 1.04 | 153 |
| 29.0 | 7,997 | 7.79% | 6.06% | 1.73% | 2.9 | 1% | 1.23 | 154 |
| 36.0 | 44,084 | 4.41% | 3.74% | 0.67% | 1.1 | 1% | 1.18 | 500 |
| 27.0 | 1,664 | 2.88% | 2.52% | 0.36% | 0.6 | 3% | 0.95 | 754 |
| 41.0 | 531,743 | 2.18% | 1.82% | 0.36% | 0.6 | 0% | 1.00 | 457 |
| 37.0 | 33,974 | 2.54% | 2.22% | 0.32% | 0.5 | 1% | 0.96 | 763 |
| 23.0 | 1,624 | 1.66% | 1.54% | 0.12% | 0.2 | 0% | 1.02 | 669 |
| 39.0 | 2,116 | 53.92% | 53.88% | 0.05% | 0.1 | 47% | 0.95 | 734 |
| 33.0 | 12,675 | 2.60% | 2.60% | 0.01% | 0.0 | 1% | 0.95 | 700 |
| 34.0 | 27,813 | 0.95% | 0.95% | 0.00% | 0.0 | 0% | 0.96 | 700 |
| 31.0 | 9,660 | 0.92% | 0.92% | 0.00% | 0.0 | 0% | 0.97 | 700 |

## C. What the price tiers are (pricing reframe)

| price | users | top payment methods | top sign-up channels | discounted | mean paid | median tenure | prev 30-day price was the same | churn |
|---|---|---|---|---|---|---|---|---|
| 99.0 | 360,805 | 41.0 (100%) | 7.0 (100%), 9.0 (0%) | 0% | 99.0 | 397 | 98% of 99% with one | 1.81% |
| 100.0 | 27,223 | 41.0 (91%), 30.0 (9%) | 7.0 (90%), 13.0 (3%) | 0% | 100.0 | 30 | 48% of 59% with one | 0.76% |
| 129.0 | 33,868 | 41.0 (85%), 30.0 (15%), 23.0 (0%) | 7.0 (89%), 13.0 (5%) | 0% | 129.0 | 747 | 91% of 96% with one | 3.88% |
| 149.0 | 286,186 | 41.0 (41%), 40.0 (25%), 37.0 (12%) | 9.0 (43%), 7.0 (41%) | 1% | 148.0 | 731 | 98% of 99% with one | 4.18% |
| 180.0 | 52,081 | 36.0 (85%), 29.0 (15%) | 9.0 (39%), 3.0 (30%) | 0% | 179.5 | 448 | 90% of 94% with one | 4.93% |

Previous 30-day price → current price (row-normalised; -1 = some other price):

```
price       99.0   100.0  129.0  149.0  180.0
prev_price                                   
-1.0        0.007  0.034  0.014  0.195  0.750
 99.0       0.995  0.003  0.001  0.000  0.000
 100.0      0.001  0.994  0.000  0.005  0.000
 129.0      0.013  0.008  0.929  0.049  0.001
 149.0      0.007  0.005  0.004  0.977  0.007
 180.0      0.000  0.001  0.001  0.012  0.986
```

Prices offered per payment method (methods with ≥ 1,000 base users):

- pm 23: [129.0, 149.0]
- pm 27: [149.0]
- pm 29: [180.0]
- pm 30: [100.0, 129.0, 149.0]
- pm 31: [149.0]
- pm 33: [149.0]
- pm 34: [149.0]
- pm 36: [180.0]
- pm 37: [149.0]
- pm 39: [149.0]
- pm 40: [149.0]
- pm 41: [99.0, 100.0, 129.0, 149.0]

## E. Sizing: what each problem is worth

Value of keeping one subscriber = their tier's 12-month revenue R(p, c). Per monthly expiring cohort; ×12 assumes every month looks like March.

| lever | users / month | TWD (12 m) per cohort | TWD / year if every month is like March |
|---|---|---|---|
| silent churn, all methods | 4,483 | 6,252,772 | 75,033,264 |
| silent churn, at-risk methods | 2,172 | 3,095,066 | 37,140,793 |
| churn via cancel | 18,105 | 24,033,448 | 288,401,376 |
| new 99 sign-ups moved to 149 (no lost sign-ups) | 9,801 | 3,460,666 | 41,527,996 |
| recover 10% of silent churn, at-risk methods | 217 | 309,507 | 3,714,079 |
| recover 25% of silent churn, at-risk methods | 543 | 773,767 | 9,285,198 |
| recover 50% of silent churn, at-risk methods | 1,086 | 1,547,533 | 18,570,396 |

New paid 30-day subscriptions per month by first price (Sep 2016 – Feb 2017 average): {99: 9802, 100: 3626, 129: 1639, 149: 11003, 180: 8203}
- Price lever: 149 earns more than 99 unless it loses more than **25%** of the people who would have signed up at 99 (1 − R99/R149 = 1 − 1,076/1,429). This dataset cannot see sign-up conversion; only a test can.

## F. Experiment sizes (80% power, α = 0.05, two-sided, user-level randomisation)

| test | baseline churn | detect churn of | users per arm | eligible users / month | months to fill both arms |
|---|---|---|---|---|---|
| 1. payment recovery (at-risk methods) | 6.69% | 6.02% | 20,850 | 92,479 | 0.5 |
| 1. payment recovery (at-risk methods) | 6.69% | 5.35% | 4,945 | 92,479 | 0.1 |
| 1. payment recovery (at-risk methods) | 6.69% | 4.69% | 2,074 | 92,479 | 0.0 |
| 2. price 149 vs 99 on new sign-ups | 4.18% | 4.68% | 26,545 | 20,805 | 2.6 |
| 2. price 149 vs 99 on new sign-ups | 4.18% | 5.18% | 6,979 | 20,805 | 0.7 |
| 2. price 149 vs 99 on new sign-ups | 4.18% | 6.18% | 1,909 | 20,805 | 0.2 |
