-- EL2 cross-period engine (ROE/ROA): add 'ttm_duration' period_kind to
-- sec_financial_metrics ONLY. Quarterly TTM ratios (ROE/ROA = trailing-12-month
-- numerator / average balance) are not single-quarter durations; they get
-- period_kind='ttm_duration' so frontend/tooltips/Obsidian export don't mistake
-- them for ordinary single-quarter values. Annual TTM-equivalents stay
-- fy_annual_duration. facts / dimensional_facts constraints are NOT touched —
-- ttm_duration is a derived-metric-only kind.
--
-- Postgres CHECK constraints cannot be altered in place; DROP + ADD.

ALTER TABLE sec_financial_metrics DROP CONSTRAINT IF EXISTS sfm_period_kind_check;

ALTER TABLE sec_financial_metrics ADD CONSTRAINT sfm_period_kind_check CHECK (
  period_kind IN ('quarter_duration', 'fy_annual_duration', 'ytd_duration', 'instant_period_end', 'derived_q4', 'ttm_duration')
);
