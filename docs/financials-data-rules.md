# Financials Data Rules

Updated: 2026-04-22

This file is the authority for how `Financials Viewer` should interpret, store, derive, and display financial-statement data.

For per-key metric meaning, statement placement, and source mapping, use:

- `docs/financials-view-schema.md`

Rule of split:

- `financials-data-rules.md` = behavior / derivation / storage rules
- `financials-view-schema.md` = metric dictionary (`key` → meaning / source / statement)

## Scope

- Applies to:
  - `financial_facts`
  - `financial_metrics`
- `financial_supplement`
- `Financials Viewer` display logic
- Applies especially to mixed-frequency data where some values are quarter-only, some are annual-only, and some are derived.

## Table Boundaries

### `financial_facts`

- Only store values directly disclosed in official filings / XBRL.
- Do not store derived values here.
- Do not rewrite annual disclosures into fake quarterly values.
- For TWSE/TIFRS:
  - `Q4` BS values are valid quarter-end / year-end balance-sheet values.
  - `Q4` IS / CF values must be single-quarter values only if they can be correctly reconstructed.
  - If prior-period data is missing and single-quarter reconstruction is impossible, drop the value instead of writing YTD / full-year numbers into `Q4`.
  - Direct `FYxxxx` annual values disclosed in the `Q4` filing may be stored in `financial_facts` using `FYyyyy` period keys.
  - Derived annual values still must not be written into `financial_facts`.

### `financial_metrics`

- Store calculated or derived values only.
- Derived values must use explicit metric names or explicit source tags so they cannot be confused with reported values.
- Good examples:
  - `gross_margin_pct`
  - `roe`
  - `weighted_avg_shares_basic_derived`
  - `weighted_avg_shares_diluted_derived`

### `financial_supplement`

- Store values not available from XBRL but still sourced from external primary material, typically NotebookLM-backed filing queries.
- Typical uses:
  - weighted average shares from EPS footnotes
  - annual segment revenue
  - segment profit / segment operating income from filing segment notes
  - geography revenue
  - non-GAAP metrics explicitly disclosed by the company
- Do not store hand-derived values here if they belong in `financial_metrics`.

## Display Rules

### Core Principle

- `Quarterly` view must show quarterly values only.
- `Annual` view must show annual values only.
- If a value is annual-only, it belongs in `Annual`, not `Quarterly`.

### Taiwan Period-Based Statement Rules

- Applies to period-based Taiwan disclosures, including:
  - `income_statement`
  - `cash_flow_*`
  - other period-based supplement series such as annual segment/geography disclosures when present
- Applies to both storage and display logic.

Rules:

1. `Annual` must use the direct `FYxxxx` value disclosed in the `Q4` filing.
2. `Annual` must not be backfilled by summing `Q1 + Q2 + Q3 + Q4`.
3. If direct `FYxxxx` data does not exist, annual view should stay empty rather than aggregating quarterly values.
4. `Quarterly` must use the direct single-quarter value for `Q1` to `Q3`.
5. For Taiwan `Q4`, quarterly period values must be reconstructed as:
   - prefer `Q4 = FY - cumulative-to-date`
   - for amount items only, if cumulative-to-date is unavailable but `Q1~Q3` direct quarter values all exist, fallback to `Q4 = FY - (Q1 + Q2 + Q3)`
6. If required prior periods or direct `FY` values are missing, leave the cell empty instead of writing a fallback value.
7. This rule overrides generic annual aggregation logic for Taiwan tickers.

### Taiwan EPS Rules

- `basic_eps` / `diluted_eps` in TWSE XBRL `Q4` are typically full-year values.
- `Quarterly` mode must show single-quarter EPS only.
- Therefore, for Taiwan `Q4`:
  - do not keep the raw annual EPS as the displayed quarterly value
  - reconstruct `Q4` single-quarter EPS as:
    - preferred: `Q4 EPS = FY EPS - 9M cumulative EPS`
    - fallback only if cumulative EPS is unavailable: `Q4 EPS = FY EPS - (Q1 EPS + Q2 EPS + Q3 EPS)`
  - only write that reconstructed `Q4` EPS into `financial_facts` if the required source values exist
  - if reconstruction is impossible, drop `Q4` EPS from quarterly storage/display rather than writing the annual value into `Q4`
- `Annual` mode should use the direct `FY` EPS disclosed in the `Q4` filing.
- If direct `FY` EPS is absent, annual EPS should remain empty instead of being recomputed from quarterly values.

### Taiwan Weighted Average Shares Rules

- Annual report weighted-average shares are annual values, not `Q4` single-quarter values.
- If the company only discloses annual weighted-average shares:
  - annual reported value may remain available for annual use
  - `Quarterly` mode should not show that annual value in `Q4`
  - if a `Q4` single-quarter share count is derived, it must live in `financial_metrics`
  - derived `Q4` share counts must be marked as derived in the UI

### Segment / Geography Rules

- Annual disclosures must use `FYxxxx` period keys.
- Quarterly disclosures must use `Qx_FYyyyy` period keys.
- `Annual` view should prefer direct `FY` values.
- For Taiwan, if no direct `FY` values exist, annual view should remain empty rather than summing quarterly values.
- For additive segment revenue series, `Q4` may be reconstructed as `FY - (Q1 + Q2 + Q3)` when:
  - direct `FY` segment values exist
  - direct `Q1~Q3` single-quarter segment values all exist
- Reconstructed `Q4` segment rows must keep explicit derived provenance and must not pretend to be direct quarter disclosures.
- Geography rows should remain direct-disclosure-only unless the company provides a quarter-compatible additive series and the derivation rule is explicitly documented.

## Provenance / UI Notes

- Any value that is not a plain direct quarter fact should carry explicit provenance when feasible.
- Direct annual facts stored with `FYyyyy` periods may use an annual-direct source tag for hover notes.
- Reconstructed `Q4 EPS` should surface a cell-level note in the UI so the user can tell whether the value came from:
  - `FY - 9M cumulative EPS`
  - `FY - (Q1 + Q2 + Q3)`

## Derivation Rules

- A derived value must satisfy all three:
  - formula is explicit
  - provenance is explicit
  - UI clearly indicates it is derived when shown alongside reported values

### Allowed

- `Q4` Taiwan period-based amount values reconstructed from `FY - cumulative-to-date`, with a secondary fallback to `FY - sum(single-quarter values)` only when the item is additive and all source quarters are directly disclosed
- additive Taiwan segment revenue `Q4` reconstructed from direct `FY - (Q1 + Q2 + Q3)` with explicit derived provenance
- `Q4` weighted-average shares derived from annual and `Q1` to `Q3` single-quarter net income / EPS
- ratio metrics
- annual aggregations built from valid quarterly values

### Not Allowed

- writing derived values into `financial_facts`
- writing annual values into quarterly slots without disclosure basis
- writing cumulative / YTD values into single-quarter display slots

## Source Priority

1. Official XBRL / filing text
2. NotebookLM query over uploaded official filings
3. Derived metrics with explicit formula and source tag

If two sources conflict:

- official filing disclosure wins over supplement
- supplement wins over heuristic UI fallback
- derived values should never overwrite reported values

## Change Discipline

When changing financial data behavior:

1. Update this file if the rule changes.
2. Update `docs/STATUS.md` if shipped behavior changes.
3. Update any relevant skill docs if parser or supplement workflow changed.
4. Do not introduce one-off ticker logic without documenting why it exists.
