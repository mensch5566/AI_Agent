# AI_Agent Status

Updated: 2026-05-14

## Current Focus
- Portal remains the main entrypoint for internal tools.
- `Financials Viewer` now includes a `Valuation` tab for historical TTM P/E with `日 / 月 / 季` switching.
- Weekly research workflow is being standardized through reusable skills such as `macro-weekly-news`.
- TWSE XBRL ingestion now also supports onboarding new tickers such as `7769 鴻勁` into `Financials Viewer`.

## Stable Areas
- `app/page.tsx` portal card layout is the top-level navigation surface.
- `app/financials/` is the main equity fundamentals workspace.
- `macro-weekly-news` workflow and related guide logic have been externalized into global skill config rather than kept only in-session.

## In Progress
- Historical valuation data currently comes from Yahoo price history + quarterly EPS reconstruction.
- Some newer tickers may not yet have enough quarterly EPS history to compute `TTM P/E`; these should render a readable empty state instead of a hard failure.
- Financials and valuation data still come from different sources and are not yet unified behind one data contract.
- TWSE XBRL onboarding still lacks automatic supplement ingestion; `financial_supplement` rows such as weighted-average shares are currently patched in separately when needed.

## Known Gaps
- No formal app-level product spec or module ownership map yet.
- No normalized status/update discipline existed before this file.
- No dedicated regression test coverage yet for the new valuation data flow.

## Development Rules Going Forward
- Update this file after any meaningful feature, data-source, or workflow change.
- For user-facing features, record:
  - what shipped
  - what data source it depends on
  - what is still incomplete or risky
- Prefer adding new portal-facing features behind an existing module/page when possible, instead of creating duplicate entrypoints.

## Latest Changes
- **Phase 3 vendor-grade SEC parse pipeline merged to production** (CC_Switch_Config `0e2d9ef`). `parse-10QK-gaap` and `parse-SEC-supplement` now produce vendor-grade separated outputs using all four XBRL linkbases (cal / pre / lab / def) plus the raw instance document, alongside the existing inline `{T}_gaap.json` (which `parse-sec-cross-check` still reads).
  - `parse-10QK-gaap` adds three scripts: `full_linkbase.py` (fetches `_cal.xml` / `_pre.xml` / `_lab.xml`, emits `_gaap_edges_cal.json` / `_gaap_edges_pre.json` / `_gaap_labels.json` / `_sign_flip_concepts.json`), `build_separated.py` (orchestrates inline → separated facts + injects long-tail roll-up edges into cal), `cal_sum_sanity.py` (validates Σ(child × weight) = parent against companyfacts API, per-role to avoid duplicate-role double-count).
  - `parse-SEC-supplement` switches default flow from NLM-primary to XBRL-primary: `parse_def_xml.py` (Definition Linkbase → canonical axis / domain / member hierarchy per filing role), `parse_instance_xbrl.py` (instance doc → raw dimensional facts, period-filtered to single quarter 60-100d or FY 350-380d, prior-year / YTD discarded), `extract_supplement_v3.py` (def + instance + parse-10QK-gaap labels + legacy NLM validator → facts_v3 + edges_v3 + validation.md). NLM-only fallback workflow retained for cases XBRL lacks dimensional tags (small filers, carve-out periods).
  - End-to-end verified on INTC (5 periods) / AAOI (13) / SNDK (4): cross-check 22/22 ticker-periods 100% pass (393 rows, 0 ❌, 0 ⚠), cal sum sanity 204 ✅ / 0 ❌ / 86 partial / 26 skipped, AAOI XBRL ↔ NLM 3 ✅ / 0 ❌ / 106 XBRL-only (XBRL is more complete than NLM-derived).
- Parsed `AAOI` (Applied Optoelectronics, CIK 0001158114) from `Q1_FY2023` to `Q1_FY2026` end-to-end. GAAP via `parse-10QK-gaap` (IS 273 rows / BS 357 / CF 220), cross-check via `parse-sec-cross-check` against NotebookLM at 215 ✅ + 18 sign-flipped / 0 ❌ / 0 N/A, Non-GAAP via `parse-8k-nongaap` (6 spine metrics × 10 periods = 55 rows including `adjusted_ebitda`).
- Small-cap parse support hardened in three SEC skills (exposed by AAOI, which prints in thousands and disaggregates SG&A):
  - `parse-10QK-gaap` now auto-detects per-ticker USD reporting scale (`infer_usd_scale`: max revenue ≥ $1B → `USD_millions`, else `USD_thousands`). Each row carries its own `unit` field; downstream consumers should never assume a default scale.
  - `parse-10QK-gaap` SG&A composite fallback: when filer has no `SellingGeneralAndAdministrativeExpense` tag, sum the standard us-gaap sub-tags into the core key AND preserve sub-values as `operating_expense_long_tail` rows (`rolls_up_to=selling_general_administrative`) so granularity isn't lost.
  - `parse-sec-cross-check` reconciles NLM ↔ SEC scales using the SEC row's `unit` (AAOI thousands ↔ thousands and INTC millions ↔ millions both compare 1:1). Adds Basic/Diluted disambig by unit and aggregates `Sales and Marketing` + `General and Administrative` for composite SG&A comparison.
  - `parse-8k-nongaap` adds `adjusted_ebitda` to the canonical Non-GAAP metric keys (small-cap spine metric).
- INTC regression validated (95 ✅ / 0 ❌ / 0 N/A unchanged after structural fixes).
- Renamed the US SEC skill to `parse-sec-filing` so it now mirrors `parse-twse-ixbrl` naming.
- Replaced the US SEC skill's old export-oriented workflow with a direct Supabase ingestion flow via `Tools/research-tools/parse-sec-filing/batch_parse.py`.
- `parse-sec-filing` now canonicalizes US XBRL output into `Financials Viewer` schema keys and writes directly to `financial_companies`, `financial_facts`, and `financial_metrics`, with JSON retained only as an audit artifact.
- Live-smoke-tested the new `parse-sec-filing` ingestion on `INTC`; Supabase now contains canonical `INTC` rows in all three tables.
- Supplemented `INTC` business-segment revenue and operating income rows in `financial_supplement` from NotebookLM (`INTC - Intel Corporation - Official Materials`) for `Q1_FY2024` to `Q3_FY2025`, direct `FY2024` / `FY2025` annual values, and `Q1_FY2026`, storing only non-overlapping leaf business segments (`CCG`, `DCAI`, `Intel Foundry`, `All Other`) so `Financials Viewer` segment totals remain meaningful.
- Expanded the US SEC ingestion/display path so filing-native Intel income-statement rows such as restructuring charges, intangible amortization, gains/losses on equity investments, non-controlling-interest income, and weighted-average shares can flow through `parse-sec-filing` into `Financials Viewer`; `INTC` also now uses ticker-specific filing-style income-statement labels plus synthetic display rows for `Operating expenses` and total `Net income (loss)`.
- Taiwan direct `FY` annual period-based values are now stored as direct `FYyyyy` rows in `financial_facts` with annual-direct provenance, while quarterly views stay clean by filtering periods instead of hiding those rows in a side path.
- Fixed `Financials Viewer` annual aggregation so direct `FYxxxx` disclosures are preserved and preferred over quarterly fallback aggregation, which restores correct annual segment / geography display for Taiwan supplement data such as `2308 台達電`.
- Re-parsed `2454 聯發科` local TWSE MOPS iXBRL files so stale `Q4_FY2025` annual EPS values in quarterly storage were replaced with reconstructed single-quarter EPS. Taiwan `Q4 EPS` now prefers `FY - 9M cumulative EPS`, and only falls back to `FY - (Q1 + Q2 + Q3)` if cumulative EPS is unavailable.
- `Financials Viewer` tables now support cell-level provenance markers so annual-direct rows and reconstructed `Q4 EPS` can show a hover note on the specific cell.
- Added `2308 台達電` to `Financials Viewer`.
- Parsed local TWSE MOPS iXBRL files for `2308` from `Q1_FY2021` to `Q4_FY2025` into Supabase via the existing `parse-twse-ixbrl` workflow.
- Supplemented `2308` segment revenue from NotebookLM (`2308 - 台達電 - 財報`) for `Q1_FY2024` to `Q3_FY2025` plus direct `FY2024` / `FY2025` annual values, and supplemented annual geography revenue for `FY2024` / `FY2025` in `financial_supplement`.
- Added derived `2308` `Q4_FY2024` / `Q4_FY2025` segment revenue rows to `financial_supplement` using `FY - (Q1 + Q2 + Q3)` with explicit source `DERIVED_Q4_SEGMENT_FROM_FY_MINUS_Q1_Q2_Q3`.
- Supplemented `2308` business-segment profit rows from NotebookLM for `Q1_FY2024` to `Q3_FY2025` plus direct `FY2024` / `FY2025` annual values, and added derived `Q4_FY2024` / `Q4_FY2025` segment profit rows using `FY - (Q1 + Q2 + Q3)` with explicit source `DERIVED_Q4_SEGMENT_PROFIT_FROM_FY_MINUS_Q1_Q2_Q3`. `Financials Viewer` / `SegmentTable` now expose this as `profit_by_business` and suppress the pie chart when negative segment values are present.
- Added a `Business P&L` card to `Financials Viewer` `Segments` tab for business segments. It shows Revenue, derived Cost, Profit, and derived Margin for each segment using the existing `revenue_by_business` / `profit_by_business` series.
- Added `7769 鴻勁` to `Financials Viewer`.
- Parsed local TWSE MOPS iXBRL files for `Q1_FY2025` to `Q4_FY2025` plus `Q4_FY2024` into Supabase.
- Updated the TWSE parser so it auto-upserts a minimal `financial_companies` row before writing `financial_facts`, preventing new-ticker foreign key failures.
- Removed invalid `Q4_FY2024` `IS/CF` rows for `7769` because `Q3_FY2024` is not present locally.
- Updated the TWSE parser so missing prior-period files now cause incomplete `IS/CF` rows to be dropped instead of writing YTD/full-year values into single-quarter periods.
- Supplemented `7769` weighted average basic/diluted shares in `financial_supplement` from NotebookLM MCP (`7769 - 鴻勁 - 財報`), using quarter values for `Q1` to `Q3` and annual values for `Q4`.
- Added `7769` `Q4_FY2025` derived weighted-average basic/diluted shares to `financial_metrics`, and updated `Financials Viewer` quarterly income-statement rendering to read those `derived` metrics instead of computing Q4 shares in the browser at render time.
- Added `7769` annual product-segment revenue rows from NotebookLM MCP into `financial_supplement` for `FY2024` and `FY2025`, and updated the segment views so direct `FY` disclosures show only in Annual mode. The consolidated filings do not disclose geography revenue splits or quarterly segment revenue splits.
- Added ticker-specific label overrides for `7769` in `Financials Viewer` so Balance Sheet and Cash Flow rows use the Chinese wording from the company’s consolidated reports rather than generic TIFRS labels.
- Added `docs/financials-data-rules.md` as the formal authority for financial statement storage/display rules, and linked `AGENTS.md` / `CLAUDE.md` to it.
- Updated the TWSE parser so Taiwan `Q4` EPS (`basic_eps` / `diluted_eps`) are reconstructed as single-quarter values via `FY - Q1 - Q2 - Q3` when all required quarter EPS values exist, instead of storing the annual `Q4` filing disclosure directly in quarterly facts.
- Updated annual aggregation rules so annual EPS is built from four single-quarter EPS values, while quarterly mode still blocks annual-only weighted-average share counts from being shown in `Q4`.
- Clarified the documentation split:
  - `docs/financials-data-rules.md` governs storage/derivation/display behavior
  - `docs/financials-view-schema.md` is the `key -> meaning/source` metric dictionary

## Next Suggested Steps
- Add lightweight regression coverage for `/api/valuation/[ticker]`.
- Decide whether valuation should stay Yahoo-based or move to a first-party normalized market-data pipeline.
- Create a small architecture note for portal module boundaries if feature count keeps growing.
