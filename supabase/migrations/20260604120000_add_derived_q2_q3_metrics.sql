-- derive-base Q2/Q3 single-quarter reconstruction (P2.1): add 'derived_q2' and
-- 'derived_q3' period_kind to sec_financial_metrics ONLY.
--
-- Background: after the 2026-05-17 "YTD first-class" parse change, the parser
-- stopped silently back-computing single quarters and instead discloses 6M/9M
-- YTD cumulatives. derive-base previously rebuilt only Q4 (FY-9M), so re-parsed
-- YTD-CF tickers (INTC/AAOI/SNDK) lost their Q2/Q3 single-quarter IS/CF flows
-- (OCF/capex/D&A). derive-base now rebuilds them too: Q2 = 6M-Q1, Q3 = 9M-6M,
-- emitted as period_kind='derived_q2' / 'derived_q3' (mirrors derived_q4).
--
-- These are derived-metric-only kinds (like derived_q4 / ttm_duration). The
-- facts / dimensional_facts constraints are NOT touched — parse never emits
-- derived single quarters (Parse-no-compute rule).
--
-- Postgres CHECK constraints cannot be altered in place; DROP + ADD.

ALTER TABLE sec_financial_metrics DROP CONSTRAINT IF EXISTS sfm_period_kind_check;

ALTER TABLE sec_financial_metrics ADD CONSTRAINT sfm_period_kind_check CHECK (
  period_kind IN ('quarter_duration', 'fy_annual_duration', 'ytd_duration', 'instant_period_end', 'derived_q4', 'derived_q2', 'derived_q3', 'ttm_duration')
);
