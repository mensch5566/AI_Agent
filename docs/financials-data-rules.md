# Financials Data Rules

Updated: 2026-05-16

This file is the authority for how `Financials Viewer` should interpret, store, derive, and display financial-statement data.

For per-key metric meaning, statement placement, and source mapping, use:

- `docs/financials-view-schema.md`

Rule of split:

- `financials-data-rules.md` = behavior / derivation / storage rules
- `financials-view-schema.md` = metric dictionary (`key` → meaning / source / statement)

## Scope

This file covers two parallel rule sets:

- **§ TWSE (legacy)** — applies to existing `financial_facts` / `financial_metrics` / `financial_supplement` (TWSE iXBRL pipeline)
- **§ SEC v2** — applies to new `sec_financial_*` tables (US SEC pipeline). 美股已從舊三表完全切換到 v2；舊三表在 v2 migration 後 drop。

- `Financials Viewer` display logic
- Applies especially to mixed-frequency data where some values are quarter-only, some are annual-only, and some are derived.

---

## SEC v2 Rules (`sec_financial_*` tables)

Authority dictionary: [`docs/sec-financials-v2-schema.md`](./sec-financials-v2-schema.md)
Design rationale: `tmp/financials-viewer-redesign-plan.md` §20 (v5.1)

### Table Boundaries (SEC v2)

#### `sec_financial_facts`

- Only direct disclosed facts (GAAP from XBRL primary; NON_GAAP from 8-K management disclosure).
- `status` constrained to `SOURCE_OF_TRUTH`. No derived values.
- `version IN ('GAAP', 'NON_GAAP')`.
- `statement IN ('IS', 'BS', 'CF', 'RATIO')` — RATIO 用於 8-K 直接揭露的 GM% / OM% 等。
- Q4 single-quarter IS / CF 不寫進這張表（要 derive → 走 metrics）。
- Q4 BS 寫進這張表（point-in-time direct fact）。

#### `sec_financial_metrics`

- All derived values：Q4 single-quarter IS / CF（`derived_q4`）、margin ratios、TTM、average balances...
- `status IN ('DERIVED_FROM_DISCLOSED', 'EXCLUDED_FROM_NONGAAP')`.
- `provenance.formula` 必填，`provenance.inputs` 帶 cell_id 回指 facts。
- **`NOT_DISCLOSED` 不寫進 DB**：由 API/read model 補 PENDING 給前端顯示 `—`。

#### `sec_financial_dimensional_facts`

- segment / geography / customer_concentration / business_segment 多軸 facts。
- grain 跟 consolidated facts 不同，不混。
- `member_key` = `member_qname` or `normalize_member_label(member)`；identity / hash / dedupe 全用 `member_key`。

#### `sec_financial_edges`

- calc / presentation / def_linkbase edges（XBRL structural knowledge）。
- 不參與 Viewer 顯示；給 anchor audit / future wiki ingest 用。

### Derive Discipline (SEC v2)

1. **derive-analytics 不可覆寫 facts 同 key**：upsert 前先 SELECT facts，存在就 skip 不寫 metrics（disclosed 優先於 derived）。此 facts-wins 護欄在 storage boundary 已廣義到**全 statement**（非只 RATIO）+ 分頁，所以 CF/IS 的絕對值衍生（FCF/EBITDA）也受保護。
2. **公式必須存進 `provenance.formula`**：例如 `FY2025 - Q1_FY2025 - Q2_FY2025 - Q3_FY2025`。
3. **inputs cell_id 必須回指**：方便 audit trail。
4. **NOT_DISCLOSED 不寫 DB**：避免「pipeline 未跑」/「derive 失敗」/「公司未揭露」三種狀態混淆。
5. **derive-analytics 可輸出非 RATIO 絕對值（Phase B）**：除了 `statement='RATIO'` 的比率，也可輸出落在原生 statement 的絕對值衍生（`free_cash_flow` → `statement='CF'`、`unit=USD`）。
   - **FCF sign**：SEC `capital_expenditures` 存**正值** cash outflow → `FCF = net_cash_from_operating − capital_expenditures`（**禁用** TWSE 相加 pattern）。負 FCF 正常。
   - period_kind：CF-derived → duration（quarterly `quarter_duration ∪ derived_q4`；annual `fy_annual_duration`）；YTD skip。unit 沿用輸入 facts 的 per-ticker scale（多 unit 不一致則 skip）。
   - payload key：canonical `analytics_metrics`（舊 `ratio_metrics` 過渡期相容）。

### Disclosed Ratio Routing (SEC v2)

Non-GAAP IS array 中 `uni_account` 命中 `RATIO_UNI_ACCOUNTS` allowlist（見 `sec-financials-v2-schema.md` §4.1）→ route 到 `statement='RATIO'`，不是 `IS`。

Safety net：`unit ∈ PCT_UNITS` 且 `uni_account.endswith('_pct')` 或 `'margin' in uni_account` → 也 route RATIO。

### Pct Value Scale (SEC v2)

- **僅適用 pct-style ratio（margins / ETR）**：DB 存小數 0~1，例如 39.2% 存 `0.392`。
- adapter 對 pct-style `unit='Pure'` row 跑 `normalize_pct_value()`：`abs(value) > 1` 時 `value/100`。
- **multiple-style ratio（current/cash/quick ratio、debt_to_equity、interest_coverage、`asset_turnover`，在 `RATIO_AS_MULTIPLE`）原樣存**（current_ratio 4.49 存 `4.49`，不可被 normalize 成 0.0449），可 >1 或為負；UI 顯示 `x`。⚠️ 目前無「揭露的倍數 ratio fact」，故 `normalize_pct_value` 對倍數的潛在 /100 尚無實害；若未來新增此類 disclosed fact，adapter 要排除 `RATIO_AS_MULTIPLE` keys。
- **days-style ratio（`dso` / `dio` / `dpo` / `ccc`，在 `RATIO_AS_DAYS`）原樣存**（值即天數本身，例 DSO 49.3 存 `49.3`，**不** ×100），CCC 可為負；UI 顯示「49.3 days」、chart 走獨立 `days` 軸（`chartGroupOf`）。`unit` 仍 `Pure`（days 是第三種 display category，非 storage unit）。⚠️ `dpo` 用 COGS 當 purchases 代理（真 purchases = COGS + Δinventory，會引入 derived-on-derived + 更多異常值，不適合 Phase 1 core key）。
- **YoY ratio（`revenue_yoy` / `net_income_yoy` / `eps_diluted_yoy`）是 duration RATIO、pct-style**（存小數，例 21.0% 存 `0.21`，UI ×100）。口徑：`(current − year_ago) / year_ago`，**`prior ≤ 0` 不產 row**（從非正基數的成長率無穩定解讀；N/M 由 read-model/display 層推導，不寫進 metrics）。period_kind：quarterly 繼承 current fact 的 kind（`quarter_duration ∪ derived_q4`，Q4 = derived_q4），annual = `fy_annual_duration`，**永不 ttm_duration**（故不在 `TTM_RATIO_ROWS`，走 quarterly fallthrough）。`period_start = None`（FactRow 無 duration startDate）。EPS 無 derived_q4（不可加）→ eps_diluted_yoy 季度只 Q1–Q3。
- pct-style UI 顯示 `fmtPct(decimal) → "${(decimal*100).toFixed(1)}%"`。`Pure` 共三種 display：pct-style / multiple-style（`x`）/ days-style（`days`）。

### Unit Canonicalization (SEC v2)

adapter 必須將 raw unit 映射到下列五種之一（其他 → validation error）：

| canonical | raw 涵蓋 |
|---|---|
| `USD_thousands` | `USD_thousands` / `thousands of USD` / `USD`+decimals=-3 |
| `USD_millions` | `USD_millions` / `millions of USD` / `USD`+decimals=-6 |
| `USD_per_share` | `USD_per_share` / `USD/share` / EPS context 的 `USD` |
| `millions_shares` | `millions_shares` |
| `Pure` | `Pure` / `percent` / `Percent` |

### Dimensional Dedupe (SEC v2)

- `member_key` 取 `member_qname or normalize_member_label(member)`，已知 alias 進 `MEMBER_ALIAS_MAP`（`Tools/research-tools/_shared/dimensional_aliases.py`）。
- 同 dedupe key 多 source（10-Q vs 8-K）value 一致 → dedupe 成一筆，`provenance.sources[]` 保留 multi-source raw label。
- value 不一致 → 整個 dimensional batch fail，寫 `validation_conflicts.md`，等人工拍板。

### Display Rules (SEC v2 statement-aware)

| view | statement | 撈 period_kind |
|---|---|---|
| quarterly IS / CF | IS / CF | `quarter_duration` ∪ `derived_q4` |
| quarterly RATIO — duration（margins / ETR）| RATIO | `quarter_duration` ∪ `derived_q4` |
| quarterly RATIO — BS-derived（current_ratio / cash_ratio）| RATIO | `instant_period_end`（period = Qx_FYyyyy） |
| quarterly RATIO — TTM-derived（EL2 roe / roa / asset_turnover / dio / dso / dpo / ccc）| RATIO | `ttm_duration`（period = Qx_FYyyyy = TTM 結束季） |
| quarterly BS | BS | `instant_period_end`（period = Qx_FYyyyy） |
| annual IS / CF | IS / CF | `fy_annual_duration` |
| annual RATIO — duration（含 EL2 roe / roa / asset_turnover / dio / dso / dpo / ccc annual）| RATIO | `fy_annual_duration` |
| annual RATIO — BS-derived | RATIO | `instant_period_end`，`Q4_FYyyyy` remap 成 `FYyyyy` |
| annual BS | BS | `instant_period_end`，`Q4_FYyyyy` remap 成 `FYyyyy` |

> RATIO 有三種 period 語意：margin / ETR 是 IS-derived（duration，跟 IS/CF 同）；current_ratio / cash_ratio / debt_to_equity 是 BS-derived（instant，跟 BS 同，annual 時 `Q4_FYyyyy` instant remap 成 `FYyyyy`）；**EL2 TTM-derived（`roe` / `roa` / `asset_turnover` / `dio` / `dso` / `dpo` / `ccc`）**（quarterly 用 `ttm_duration` + `TTM_RATIO_ROWS` allowlist，annual 用 `fy_annual_duration`）。前端 `useFinancialMatrix` 依此分流。

Status-aware render：

| status | UI |
|---|---|
| `SOURCE_OF_TRUTH` | 黑字 |
| `DERIVED_FROM_DISCLOSED` | 灰字 + tooltip 顯示 `provenance.formula` |
| `EXCLUDED_FROM_NONGAAP` | 空白 + tag "excluded" |
| row 不存在 | `—` + tag "pending" |

### Non-GAAP UI (SEC compliance)

- GAAP 主表優先或同等顯著。
- Non-GAAP 不做 version toggle（不切換成完整 Non-GAAP P&L）。
- 6 個 spotlight metric（revenue / gross_profit / operating_income / net_income / eps_diluted / adjusted_ebitda）顯示為 **GAAP 旁的並列欄**。
- ReconciliationPanel（adjustment detail）為 Phase 2，需 `parse-8k-nongaap` 擴充抽 adjustments + 新表 `sec_nongaap_adjustments`。

### Sign-Flip Display

- `sec_financial_companies.sign_flip_concepts jsonb` 列出該 ticker 有 `negatedLabel` role 的 XBRL concept。
- 前端 render facts 時：`if (fact.xbrl_tag in sign_flip_concepts) → 顯示時加括號表示為負`。

---

## TWSE (Legacy) Rules — applies to old `financial_facts` / `financial_metrics` / `financial_supplement`

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
