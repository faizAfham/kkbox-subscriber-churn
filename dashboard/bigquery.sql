-- BigQuery layer for the Looker Studio dashboard. Project kkbox-churn-1123fa, dataset kkbox (US).
-- kkbox.subscribers is loaded from data/dashboard/kkbox_subscribers.csv.gz (kaggle/kkbox-dashboard-export):
-- one row per paying, auto-renewing 30-day subscriber whose plan expired in March 2017 (760,163 rows).
-- One wide view, so every chart shares one data source and every filter control works on every chart.
-- Rates are AVG of 0/1 columns; money is SUM.
create or replace view kkbox.v_dashboard as
select
  user_id,
  churned,
  if(churn_type = 'cancelled', 1, 0)                         as churn_cancel,
  if(churn_type = 'silent', 1, 0)                            as churn_silent,
  churn_type,
  price,
  cast(price as string)                                      as price_tier,
  payment_method,
  cast(payment_method as string)                             as payment_method_label,
  case when payment_method in (40, 30, 29) then 'At-risk methods (40, 30, 29)'
       when payment_method = 41 then 'Method 41 (main)'
       else 'Other methods' end                              as method_group,
  tenure_days,
  case tenure_band when '<1y' then 'Under 1 year' when '1-2y' then '1-2 years' else 'Over 2 years' end as tenure_band,
  registered_via                                             as signup_channel,
  coalesce(feb_days, 0)                                      as feb_listening_days,
  feb_band                                                   as feb_listening_band,
  case feb_band when '0 d' then 0 when '1-7 d' then 1 when '8-14 d' then 2 when '15-21 d' then 3 else 4 end as feb_band_order,
  trend                                                      as listening_trend,
  low_listening_flag,
  value_12m_twd,
  if(churned = 1, value_12m_twd * 12, 0)                     as twd_lost_per_year   -- one March-like cohort x 12 months
from kkbox.subscribers;

-- sanity check: must match analysis/results/phase3/drivers.md (760,163 users, 2.97% churn, 2.38% cancel, 0.59% silent)
select count(*) users, round(avg(churned) * 100, 2) churn_pct,
       round(avg(churn_cancel) * 100, 2) cancel_pct, round(avg(churn_silent) * 100, 2) silent_pct
from kkbox.v_dashboard;
