# Building the Looker Studio dashboard (about 30–40 minutes)

**Built 2026-11-24 (by Claude via Playwright, in Faiz's account):** https://lookerstudio.google.com/reporting/62de4d11-cf01-48a9-91dc-e3198d6fdd19
Pages: Overview · Silent exits · Engagement · Price (chart filter: payment method 41) · What to fix first (from views v_sizing_display, v_experiments_display).
Differences from the plan below: report-level calculated fields (Churn rate, Left via cancel, Left silently, Subscribers, TWD lost per year, Revenue per subscriber 12m, Band order) replace per-chart aggregation; Looker's default colours, not Wada #247. The steps below remain as the rebuild recipe.

Data is already in BigQuery: project `kkbox-churn-1123fa`, dataset `kkbox` (SQL in `bigquery.sql`).
Open the link in `create_report_url.txt`. It creates a new report with all four data sources connected:
`v_dashboard` (one row per subscriber), `payment_methods`, `sizing`, `experiment_sizes`.
If Looker Studio asks to authorise BigQuery, click **Authorize** and pick the same Google account.

Conventions used below:
- "Add chart" = toolbar → **Add a chart**. "Data panel" = the right-hand panel after selecting a chart (Setup tab).
- To change a metric's aggregation, click the small icon left of the metric name → **Aggregation**.
- To show a metric as a percentage: same menu → **Type** → Numeric → **Percent**.
- Colours (Wada #247): blue `#2A55A6`, sienna `#BB7125`, green `#00978D`, headings `#1C4286`. Set them in **Style** → Bar colours.
- Theme: **Theme and layout** → Theme → Simple, then set font to *Inter* (or Roboto if Inter isn't listed).

## Page 1 — Overview: where churn comes from

1. Rename the page (top: **Page** → Manage pages) to "Overview". Add a **Text** box title: "Where KKBox loses paying subscribers (March 2017)".
2. **Filter controls** in one row at the top (Add a control → **Drop-down list**), data source `v_dashboard`:
   - Control field `method_group`
   - Control field `price_tier`
   - Control field `tenure_band`
3. **Five scorecards** (Add chart → Scorecard), data source `v_dashboard`:
   | Scorecard | Metric | Aggregation | Format | Rename to |
   |---|---|---|---|---|
   | 1 | Record Count | — | Number | Subscribers |
   | 2 | `churned` | Average | Percent | Churn rate |
   | 3 | `churn_cancel` | Average | Percent | Left via cancel |
   | 4 | `churn_silent` | Average | Percent | Left silently |
   | 5 | `twd_lost_per_year` | Sum | Number, compact | TWD lost / year |
4. **Bar chart: churn by price, split by type.** Add chart → **Stacked column chart**.
   Dimension `price_tier`; metrics `churn_cancel` (Average, Percent) and `churn_silent` (Average, Percent).
   Sort: `price_tier` ascending. Style: series 1 blue, series 2 sienna; show data labels.
   Title: "Cancellations rise with price; silent exits don't".
5. Check: with no filters, the scorecards should read 760,163 · 2.97% · 2.38% · 0.59%.

## Page 2 — Silent exits by payment method

1. Add page "Silent exits". Copy the three filter controls from page 1 (Ctrl+C / Ctrl+V); they keep working.
2. **Bar chart** (Add chart → **Bar chart**, horizontal), data source `payment_methods`:
   dimension `pm`, metric `churn_silent` (Average, Percent). Sort `churn_silent` descending. Colour sienna.
   Title: "Three methods run 2–4× the average silent churn".
3. **Table**, data source `payment_methods`: dimensions `pm`; metrics `users` (Sum), `churn`, `churn_cancel`, `churn_silent` (Average, Percent), `tenure_median_days` (Average).
   Style → **Conditional formatting** on `churn_silent`: background sienna when > 0.0118 (twice the 0.59% average).
4. **Stacked column chart**, data source `v_dashboard`: dimension `feb_listening_band`; metrics `churn_cancel`, `churn_silent` (Average, Percent).
   Sort by `feb_band_order` (Min) ascending. Title: "Heavy listeners cancel less but leave silently more → failed payments".

## Page 3 — Engagement before renewal

1. Add page "Engagement". Paste the filter controls.
2. **Column chart**, `v_dashboard`: dimension `feb_listening_band`; metric `churned` (Average, Percent); sort `feb_band_order` (Min) ascending.
   Title: "Listening in February barely predicts March churn".
3. **Table**, `v_dashboard`: dimension `listening_trend`; metrics Record Count, `churned`, `churn_cancel`, `churn_silent` (Average, Percent). Sort `churned` descending.
4. **Scorecards** with a chart-level filter (Setup → **Filter** → Add a filter → Include `low_listening_flag` = true):
   Record Count ("Flagged subscribers") and `churned` Average ("Churn if flagged"). Add a text box: "Flag catches 64% of cancellers but flags 52% of everyone: 1.2× lift".

## Page 4 — Price

1. Add page "Price". **Column chart**, `v_dashboard`, chart filter: Include `payment_method_label` Equal to `41`.
   Dimension `price_tier`; metric `churned` (Average, Percent). Sort `price_tier` ascending. Colour blue, 149 bar sienna (Style → Bar colours → Bar 4).
2. **Second column chart**, same filter: dimension `price_tier`; metric `value_12m_twd` (Average) renamed "Revenue per subscriber, 12 months (TWD)".
3. **Text box**: "149 earns TWD 410 more a year than 99 (CI 401–418). It stops paying only if churn reaches 9.86%, or if it loses more than 25% of sign-ups. Users almost never change tier, so a price test on new sign-ups is the next step."

## Page 5 — What to fix first

1. Add page "What to fix first". **Table**, data source `sizing`: dimension `lever`; metrics `users_per_month` (Sum) and `twd_per_year_if_every_month_like_march` (Sum, compact) renamed "TWD a year". Sort by TWD descending.
2. **Table**, data source `experiment_sizes`: dimensions `test`; metrics `baseline_churn`, `target_churn` (Average, Percent), `n_per_arm` (Sum), `months_to_fill` (Average, 1 decimal).
3. **Text box** with the priority: "1. Payment recovery test on methods 40/30/29 (~6 weeks). 2. Price test 149 vs 99 on new sign-ups. 3. Cancellations: exit survey in the cancel flow first."

## Finish

- **View** (top right) to check it, then **File → Report settings**: set the report's description. Add a footer text box on each page: "Data: KKBox, WSDM Cup 2018 (Kaggle). Annual figures = March 2017 cohort × 12."
- **Share**: Share → Manage access → "Anyone with the link can view" only when you are ready to put it on the resume/GitHub. Viewers need no BigQuery access (the report uses your credentials by default).
- **Cost**: the BigQuery sandbox is free (10 GB storage, 1 TB queries a month); this dataset is ~60 MB. Sandbox tables expire after 60 days unless billing is added; re-run `bq load` (see `bigquery.sql` header) to restore.
