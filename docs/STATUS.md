# AI_Agent Status

Updated: 2026-05-23

## Current Focus
- Portal remains the main entrypoint for internal tools.
- `Financials Viewer` now includes a `Valuation` tab for historical TTM P/E with `日 / 月 / 季` switching.
- Weekly research workflow is being standardized through reusable skills such as `macro-weekly-news`.
- TWSE XBRL ingestion now also supports onboarding new tickers such as `7769 鴻勁` into `Financials Viewer`.
- **Audit Metadata Schema v4 contract shipped end-to-end across all parse paths** (10QK GAAP / 8K Non-GAAP / SEC-supplement v3) → adapter → upsert → derive-base. Every audited / classified / preserved cell carries v4 channels through the full pipeline; 179 regression tests cover the contract.

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
- **Audit Metadata Schema v4 — Phase 4 closed** (2026-05-22 → 2026-05-23, 2 rounds of Codex review).
  - `parse-SEC-supplement/extract_supplement_v3.py` now preserves dimensional audit/classification cells across re-extracts. Identity tuple `(period, period_kind, axis_key, member_key, uni_account, canonical_json(other_dimensions), unit)` per schema §6.2 — uses `_shared/dimensional_aliases.build_axis_key()` / `build_member_key()` (xbrl qname preferred, local-label fallback).
  - Behavior matrix mirrors GAAP/8K (MATCH / ADDED_BACK / CONFLICT / ACCEPT_NEW) with same audit vs classification-only branch, legacy `AGENT_CLASSIFIED` canonicalization on ADDED_BACK, and `DuplicateIdentityError` fail-closed.
  - Supplement-specific fail-closed mechanism: AUDIT conflicts (not classification-only) get written to `{TICKER}_supplement_conflict.json` with `audit_conflicts_unresolved=true` flag (schema §5 supplement clause). User reviews each conflict, then re-runs extract with `--accept-new-values` to drop preserved audit metadata.
  - Stale conflict.json is cleaned on any rerun that produces no audit conflicts (not just `--accept-new-values`).
  - Corrupt existing facts JSON raises `ValueError` rather than silently dropping prior audit metadata.
  - `_values_match` uses `≤ tol` per schema §5 wording (exact-boundary equality counts as MATCH).
  - 23 regression tests for Phase 4 (identity tuple variants, full preservation matrix, classification-only / mixed conflicts, duplicate fail-closed, corrupt JSON, tolerance boundaries, stale cleanup).
- **Audit Metadata Schema v4 — Phase 2 + Phase 3 closed** (2026-05-21 → 2026-05-22, 11 rounds of Codex review).
  - Canonical contract: `docs/audit-metadata-schema.md` v4.1 — three semantic channels (audit / classification / preservation event), strict allowlists for each, legacy enum normalization, re-extract behavior matrix.
  - Shared helper: `Tools/research-tools/_shared/audit_metadata.py` — allowlist constants, predicates (`is_manual_audit_source` / `is_manual_classification_source`), write helpers (`stamp_audit_provenance` / `stamp_classification` with locator / accession_number enforcement), copy helpers (`copy_audit_provenance` / `copy_classification_metadata` / `set_preservation_event`), preservation identity builder (`build_preservation_identity` + `DuplicateIdentityError`), unit normalization (`normalize_unit_label` / `expected_unit_family` / `resolve_unit_for_uni_account` — recognizes `$ thousands` / `thousands of USD` / `%` / `per share` etc.).
  - Parse skills updated (`CC_Switch_Config` mirrored 4-way to `~/.claude` / `~/.codex` / `~/.cc-switch`):
    - `parse-sec-cross-check/scripts/apply_audit.py` — writes canonical `MANUAL_AUDIT_FROM_OFFICIAL_FILING` + raw dual-write + audit_evidence dict (source_doc / notebooklm_source_id / period_scope / pdf_label) + classification path for long-tail rows.
    - `parse-8k-nongaap/scripts/apply_audit.py` — same canonical write path; review-table unit canonicalized before adopting; family compatibility check vs `expected_unit_family(uni_account)`.
    - `parse-8k-nongaap/scripts/extract_8k_nongaap.py` — `is_audit_value_filled` rewritten header-aware (no longer treats NLM Non-GAAP numbers as filled audit values); `resolve_8k_unit` promoted to module-level routes through `normalize_unit_label` (removes `$`-substring bug that mapped `$ thousands` to `USD_millions`); ADDED_BACK canonicalizes legacy `audit_source=AGENT_CLASSIFIED` to `classification_source`.
    - `parse-10QK-gaap/scripts/xbrl_extract.py` — same v4 preservation matrix (MATCH / ADDED_BACK / CONFLICT / ACCEPT_NEW with audit vs classification-only branches); duplicate identity fail-closed via `DuplicateIdentityError`.
  - Adapter / upsert / derive-base (`Tools/research-tools/_shared/sec_json_adapter.py`, `scripts/upsert_sec_financials.py`, `CC_Switch_Config/skills/derive-base/scripts/*`):
    - `_carry_audit_metadata_to_provenance` — v4 three-channel allowlist-guarded carry-through. Audit channel writes only allow MANUAL_AUDIT_SOURCES; legacy `AGENT_CLASSIFIED` in `audit_source` field auto-promotes to `classification_source`; invalid enum or orphan audit detail raises `ValueError` → row goes to `rejected` list; classification channel and preservation event channel also strict allowlist.
    - `derive_types.input_dict_from_fact` — carries `audit_source` / `audit_source_raw` / `audit_evidence` from FactRow provenance for derive-base lineage.
    - `audit.to_derived_metric_row` — computes `has_audited_inputs` + `audited_input_cell_ids` so derived rows declare audit lineage back to source cells.
    - `rules_q4._concepts_match` — upgraded from truthy `audit_source` check to `is_manual_audit_source` predicate; classification rows no longer falsely trigger Q4 concept relaxation.
  - Non-GAAP adapter: hardcoded `audit_source="NotebookLM_PDF_read"` removed (it was never a v4 audit source); replaced with `provenance.data_source` so it doesn't pollute audit predicate.
  - 156 regression tests, full suite passing. Test split: 62 helper / 17 10QK preservation / 4 8K preservation / 22 8K parse / 34 adapter+derive integration / 17 misc.
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
- **Phase 5 (audit schema)**: `manual_edit.py` CLI for ad-hoc audit edits outside `apply_audit.py` flow (one-off cell corrections that aren't tied to a cross-check run). Schema v4 already supports the metadata; just needs a clean entry point + `manual_edit_audit_log.jsonl` write path.
- **Phase 6 (audit schema)**: frontend audit indicator on cells with `provenance.audit_source != null` or derived rows with `has_audited_inputs=true`; DB legacy row migration (one-shot normalize of pre-v4 `audit_source` enums in existing Supabase data); optional `_shared/preservation.py` refactor to dedupe the now-three copy-pasted `_preserve_*_cells` functions across 10QK / 8K / supplement.
- Add lightweight regression coverage for `/api/valuation/[ticker]`.
- Decide whether valuation should stay Yahoo-based or move to a first-party normalized market-data pipeline.
- Create a small architecture note for portal module boundaries if feature count keeps growing.
