# derive-analytics Phase B 本體（FCF）— Design Spec

Date: 2026-06-01 / Project: ai_agent
Status: 設計已批准（做法 A）。範圍：**只做 FCF**（Quick Ratio 留後續小單元再決命名）。

## 目標
derive-analytics 第一次輸出**非 RATIO 的絕對值衍生 row**：Free Cash Flow = `net_cash_from_operating − capital_expenditures`，`statement=CF`、`unit=USD`（per-ticker scale）。同時把 EL1 引擎從「只能算比率」擴成「也能算 numerator-only 絕對值」。

## 背景 / 不變式
- source-of-truth ONLY：parse 不算衍生；FCF 只進 `sec_financial_metrics`，不污染 `sec_financial_facts`。
- 本地 JSON 是第一線輸出（Obsidian 會用）；前端只讀 Supabase。
- 5-mirror 同步：prototype `tmp/derive-analytics/`（FLAT）→ CC_Switch_Config（canonical）→ 3 runtimes。
- Phase B 前置已把 storage facts-wins 廣義到全 statement + 分頁；FCF（CF）落地後第一次真正觸發「derived 不得覆蓋 disclosed CF fact」。

## 已查證的資料事實
- FCF 輸入 `net_cash_from_operating` + `capital_expenditures`（CF）四 ticker 皆有。
- capex 存正值（cash outflow）→ `FCF = CFO − capex`（AAOI thousands / INTC millions 皆驗）。負 FCF 正常（AAOI/INTC capex-heavy 期）。
- 6M/9M YTD 期會被引擎 YTD skip 擋掉（與既有 ratio 一致）。
- FCF 只會出現在 GAAP（無 NON_GAAP CF facts，引擎自動 skip）。

## 決定：做法 A（擴充現有 rule，不另開引擎）
A 與 B 輸出完全相同；A 不複製 term 解析/period 一致性/YTD/provenance 邏輯，符合 EL1「線性項統一各種情況」設計。C（分母=常數 1）無法表達 statement=CF/unit=USD，否決。

## 改動

### 1. 引擎 `rules_ratios.py`
- dataclass `RatioRule` → 改名 `AnalyticsRule` + 留 `RatioRule` alias。新增欄位：
  - `denominator: tuple = ()`（空 → 絕對值 numerator-only）
  - `output_statement: str = "RATIO"`、`output_unit: str = "Pure"`
- list `RATIO_RULES` → `ANALYTICS_RULES` + alias。新增 FCF rule：
  ```python
  AnalyticsRule("free_cash_flow", "FCF_CFO_MINUS_CAPEX",
      numerator=(_t("net_cash_from_operating","CF"),
                 _t("capital_expenditures","CF", coef=-1.0)),
      denominator=(), output_statement="CF", output_unit="FROM_INPUTS")
  ```
- `compute_single_period_ratios`（留 alias `compute_single_period_metrics`）分流：
  - 有 denominator → 照舊（num/den、RATIO/Pure）。6 個既有 ratio 一字不改。
  - denominator 空 → 絕對值：只 resolve numerator；period_kind/period_end 一致性 + YTD skip（只看 numerator facts）；無除零 policy；`output_unit=="FROM_INPUTS"` → 取 numerator facts 的 unit，多 unit 不一致則 skip；`value=分子總和`、`statement=rule.output_statement`、`formula` 單邊去外括號（`"net_cash_from_operating - capital_expenditures"`）。
- `ALL_RULE_IDS` 自動含 `FCF_CFO_MINUS_CAPEX`。

### 2. 輸出 `audit.py`
- `write_analytics_json`：主鍵 `"ratio_metrics"` → `"analytics_metrics"`，**保留 `"ratio_metrics"` 鏡像一個週期**（back-compat）。
- row writer 不改（statement/unit/value 已讀 candidate）；`to_ratio_metric_row` 留 alias `to_analytics_metric_row`。audit md 文案 ratio→analytics。

### 3. upsert `scripts/upsert_sec_financials.py`（AI_Agent repo，不進 mirror）
- reader：`get("analytics_metrics") or get("ratio_metrics") or []`。
- `DERIVE_ANALYTICS_RULE_IDS_FALLBACK += "FCF_CFO_MINUS_CAPEX"`（owned-scope delete + drift guard）。
- facts-wins 不動（前置已廣義）。

### 4. 前端 `app/components/financials-v2/constants.ts`
- `CF_ROWS` 在 `capital_expenditures` 後插 `{ key: "free_cash_flow", label: "Free Cash Flow", kind: "subtotal" }`。derived 樣式（italic muted）由 metrics cell 的 source_table 自動帶出，不需特別處理。
- CHART_DEFAULT_KEYS.CF 不動（FCF 可手動點選）。

### 5. docs
- `sec-financials-v2-schema.md`：登記 `free_cash_flow`（CF、derived、formula、unit=USD per-ticker、status ✅）。
- `financials-data-rules.md`：derive-analytics 現在會輸出非 RATIO 絕對值（CF）；FCF sign convention（SEC capex 為正 → 相減，禁 TWSE 相加）。

## 測試（TDD）
- prototype `tests/test_rules_ratios.py`：FCF 絕對值 rule（CFO−capex、unit 沿用、statement=CF、單邊 formula）；YTD skip；缺輸入 skip；負 FCF；6 既有 ratio regression 不變。
- `scripts/tests/test_upsert_derived.py`：reader 讀 `analytics_metrics`（+ 舊 `ratio_metrics` 相容）；fallback 含 FCF rule_id；drift guard 仍綠。
- `npx tsc --noEmit`。

## 部署 / 驗證（這次**要** re-upsert，FCF 是新 output）
- 5-mirror sync。
- 四 ticker 重跑 derive-analytics + `--apply` re-upsert（end-to-end，順帶 live 驗證非 RATIO facts-wins，如前置收尾承諾）。
- 抽期對 SEC filing 複核 FCF = CFO − capex；前端 Cash Flow 分頁 quarterly/annual 顯示 Free Cash Flow，負值正常。

## 不做（留後續）
- Quick Ratio（卡 short_term_investments 在 AAOI/SNDK 缺、命名口徑未決）。
- FCF Margin（FCF/revenue，普通 Pure ratio，後續可加）。
- Phase C EBITDA、Phase D EL2 跨期引擎、Phase E segment margin、BVPS。
