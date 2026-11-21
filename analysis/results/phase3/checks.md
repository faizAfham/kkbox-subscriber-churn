# Phase 3 checks

## 1. Cancel dates, Jan–Mar 2017 (base users)

- pm 39: 1,683 cancels on 71 distinct days; top 3 days hold 17%: {'2017-02-03': 105, '2017-02-13': 95, '2017-02-08': 82}
- pm 41: 27,587 cancels on 90 distinct days; top 3 days hold 6%: {'2017-03-15': 638, '2017-03-14': 582, '2017-03-04': 573}
- pm 40: 6,178 cancels on 90 distinct days; top 3 days hold 9%: {'2017-03-02': 209, '2017-03-07': 177, '2017-03-04': 141}
- pm 30: 2,024 cancels on 90 distinct days; top 3 days hold 10%: {'2017-03-02': 74, '2017-03-08': 73, '2017-03-09': 57}
- pm 36: 6,589 cancels on 90 distinct days; top 3 days hold 8%: {'2017-03-01': 190, '2017-03-04': 174, '2017-03-05': 131}
- method recorded on the cancel row (all base): {41: 28204, 40: 6692, 36: 5420, 39: 2004, 37: 1862}

Cancels per week (all base users):

```
transaction_date
2016-12-26/2017-01-01     183
2017-01-02/2017-01-08    2277
2017-01-09/2017-01-15    2317
2017-01-16/2017-01-22    2576
2017-01-23/2017-01-29    2092
2017-01-30/2017-02-05    2340
2017-02-06/2017-02-12    3360
2017-02-13/2017-02-19    3019
2017-02-20/2017-02-26    2978
2017-02-27/2017-03-05    5661
2017-03-06/2017-03-12    6341
2017-03-13/2017-03-19    6382
2017-03-20/2017-03-26    5511
2017-03-27/2017-04-02    3780
Freq: W-SUN
```

## 2. Inside payment method 41: sign-up channel by price

```
price            99.0   100.0  129.0   149.0
registered_via                              
7.0             283328  20618  27172  103507
9.0                326     39     54     169
```

Churn by price × channel inside pm41 (cells ≥ 1,000 users):

```
                        size    mean
registered_via price                
7.0            99.0   283328  0.0165
               100.0   20618  0.0029
               129.0   27172  0.0284
               149.0  103507  0.0324
```
