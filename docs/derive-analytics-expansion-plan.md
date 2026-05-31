# derive-analytics 擴展 Project Plan（2026-05-31）

> 目的：把 derive-analytics 從目前的 5 個單期比率 MVP，擴展成「分析師等級」的派生指標層。
> 本文件先寫**計畫**，等 GPT review 後才正式開發。本 session 已做的（3 個前端 bug fix + 4 ticker upsert）與目前前端在進行的內容，將在新計畫定案後，依新計畫重新對齊應用。
> 指標需求來源：NotebookLM `Parse_SEC_Filings`（48 sources，含 CFA NGFM 指南 / SEC Reg G / Non-GAAP handbook / vendor 實務）。

---

## GPT Review Notes（Codex review，2026-05-31）

Review basis:
- `docs/STATUS.md`
- `docs/financials-view-schema.md`
- `docs/financials-data-rules.md`
- `docs/sec-financials-v2-schema.md`
- current `derive-analytics` / `derive-base` scripts, `scripts/upsert_sec_financials.py`, and `Financials Viewer` frontend code
- memsearch context for `parse-10QK-gaap`, `parse-8k-nongaap`, `parse-SEC-supplement`, `derive-base`, and the original `derive-analytics` MVP decision

### Review 結論

方向是對的：`derive-analytics` 作為獨立於 parse / derive-base 的分析指標層，符合既有「parse source-of-truth only、derive 寫 metrics」紀律。

但目前 plan 不能直接開發，因為有幾個 contract 級問題會導致前端顯示錯值、Supabase 舊值殘留，或把 `derive-base` 的邊界打壞。以下項目應先修進 plan / spec，再進 implementation。

### P0 — 必修正

1. **derive-analytics 目前會覆蓋 direct disclosed ratio 的顯示優先權**

   `docs/financials-data-rules.md` 明確要求：disclosed ratio 進 `sec_financial_facts`，derived ratio 進 `sec_financial_metrics`，且 derive-analytics 不可覆寫 facts 同 key。plan 有寫原則，但 DoD 沒有要求具體實作。

   目前實作風險：
   - `scripts/upsert_sec_financials.py` 會直接 upsert analytics rows 到 `sec_financial_metrics`，沒有先查 `sec_financial_facts` 是否已有同一個 `(ticker, period, period_kind, version, statement, uni_account)`。
   - `/api/financials/[ticker]` 先 push facts、再 push metrics。
   - `useFinancialMatrix.ts` 對同一 row/period 是 last-write-wins，所以 metrics row 可能在前端覆蓋 facts row。

   必修：
   - 在 derive-analytics 輸出或 upsert 階段加入 `filter_against_facts`，同 identity 已有 `sec_financial_facts` 時 skip metrics row。
   - 前端/API 也應加 facts-wins 防線，避免任何未來 derived row 視覺覆蓋 SOURCE_OF_TRUTH。
   - 加 regression：同一 `RATIO` key 同時存在 facts + metrics 時，前端/API 必須顯示 facts。

2. **derive-analytics 的 delete scope 不是完整 snapshot replacement，會留下 stale rows**

   目前 `derive_analytics.py` 的 `metadata.managed_rule_ids` 是從本次 emitted rows 反推；`upsert_sec_financials.py` 只刪本次 payload 裡的 `a_managed`，沒有像 derive-base 一樣 union fallback / full owned scope。

   這會造成：某 rule 上次有輸出、這次因 input 缺失或公式改版不再輸出時，舊 Supabase row 不會被刪掉，前端繼續顯示 stale ratio。

   必修：
   - `managed_rule_ids` 必須來自 enabled rule registry，不是從 emitted rows 反推；即使本次某 rule 產 0 rows，也要列入 managed scope。
   - `upsert_sec_financials.py` 需要 derive-analytics 的 fallback / owned rule-id registry，做完整 snapshot replacement。
   - 新增 rule class（absolute / TTM / segment）時，每個 class 都要有穩定 rule registry 與 delete scope。

3. **derive-analytics 沒有 freshness gate，擴大後會產生 mixed-vintage data**

   derive-base 已有 `verify_derived_freshness()`：比對 `metadata.input_files` 的 sha256，parse output 改了就拒絕 `--apply`。derive-analytics 目前沒有；missing / incomplete 也只是 preserve old ratios。

   MVP 時 ratio 是 additive，風險較小；但如果要加入 FCF、ROE、ROA、TTM、Net Debt/EBITDA，stale analytics 會直接影響核心分析。

   必修：
   - 為 derive-analytics 建 freshness gate，至少比對 `gaap_facts`、`nongaap`（若存在）、`gaap_inline`、`derive_base`。
   - `--apply` 時 analytics latest run incomplete 或 stale，預設 fail closed；若要允許 parse-only refresh，必須 explicit flag，且清楚說明 existing analytics preserved。
   - DoD 補上 stale-run regression。

### P1 — 開發前要改設計

4. **現有 derive-analytics row schema 沒達到 metrics contract**

   plan 說每筆 derived row 要帶 `provenance.formula` + `provenance.inputs` 回指來源 cell，但目前 `derive-analytics` 實作沒有做到：
   - `cell_id` 是人類可讀字串 `derived::...`，沒有使用 `_shared.cell_id.metrics_cell_id()`，與 derive-base / DB identity contract 不一致。
   - `provenance.inputs` 只有 `uni_account/value/period/statement`，沒有 input `cell_id`，無法回指 source rows。
   - `provenance.formula` 缺失，前端 tooltip 只能顯示 `derived`。
   - 沒有像 derive-base 一樣聚合 `has_audited_inputs` / `audited_input_cell_ids`。

   必修：
   - 先把 MVP 5 ratios 的輸出升級到 derive-base 同等 contract，再擴更多 rule。
   - `to_ratio_metric_row()` 改用 `metrics_cell_id()`。
   - inputs 必須包含至少 `cell_id`、`period`、`period_kind`、`statement`、`version`、`uni_account`、`value`、`unit`，並保留 audit metadata lineage。
   - `provenance.formula` 必填。

5. **不要把 FCF / EBITDA 放進 derive-base，除非重寫 derive-base contract**

   plan 多處傾向把 FCF / EBITDA materialize 放到 derive-base，理由是 derive-base 會輸出 IS/CF/BS 絕對值。這和現有 derive-base skill 邊界衝突。

   現有 derive-base 的邊界是「填洞」：
   - Q4 reconstruction
   - same-statement subtotal identity
   - calc linkbase parent sum
   - 不做新的分析 KPI

   FCF、EBITDA、Net Debt、Invested Capital 都是分析用 KPI materialization，不是 filing subtotal 補洞。把它們塞進 derive-base 會讓 derive-base 從 gap-filler 變成 analytics engine，破壞先前四輪 review 建好的邊界。

   建議決策：
   - FCF / EBITDA / Net Debt 等 materialized analytics metrics 放在 `derive-analytics`（但 payload key 應從 `ratio_metrics` 升級為較通用的 `analytics_metrics` 或保留相容 alias）。
   - 或另開 `derive-kpi-materialize`，但不要混進 derive-base。
   - 只有在明確重寫 derive-base SKILL.md、tests、upsert delete scope、docs 後，才可讓 derive-base 接 KPI。

6. **EL2 TTM / average-balance 指標缺 period_kind / display contract**

   `sec_financial_metrics.period_kind` 目前允許 `quarter_duration` / `fy_annual_duration` / `instant_period_end` / `derived_q4` / `ytd_duration`。TTM ROE、TTM ROA、Net Debt / TTM EBITDA 不是單季 duration，也不是 FY annual。

   如果把 TTM row 存成 `period_kind='quarter_duration'`，前端能顯示，但語意會錯，之後 annual / quarterly filter、chart tooltip、Obsidian JSON 消費都會把 TTM 誤解成單季值。

   必修：
   - 在 EL2 前先定義 TTM / average-balance metrics 的 storage/display contract：是否新增 period_kind（需要 migration + frontend filter），或沿用 period label 但在 provenance 加 `window='TTM'` 並在 UI 顯示。
   - 不能無標記地把 TTM 指標偽裝成 ordinary quarter ratio。
   - annual view 要定義：顯示 FY annual ratio，還是 fiscal-year-end TTM ratio，二者不可混。

7. **Phase A 的幾個指標不是「幾乎 EL0 加 tuple」**

   Phase A 寫 Cash Ratio / Debt-to-Equity / Interest Coverage / Book Value per Share 是 4 個純單一 fact ÷ 單一 fact。這不完全成立：
   - `book_value_per_share` 需要 period-end shares outstanding；目前 schema 只有 `shares_basic_millions` / `shares_diluted_millions`（weighted-average shares，IS duration），不能拿來當 BVPS 分母。
   - `debt_to_equity` 必須先決定 debt 定義：total liabilities、interest-bearing debt、current debt + long-term debt、是否含 lease。不能用「total_liab(或 total_debt)」進 implementation。
   - `interest_coverage` 必須先定義 EBIT：`operating_income` 還是 `income_before_taxes + interest_expense`；interest expense 的正負號與 0/負值 N/M 也要定義。
   - `cash_ratio` 可做，但要確認只用 `cash_and_cash_equivalents / total_current_liabilities`；若要含短投，現有 SEC schema 沒有 short-term investments key。

   建議：
   - Phase A 只放「inputs 已存在且定義無歧義」的 rule。
   - 其餘指標先在 `docs/sec-financials-v2-schema.md` 登記 uni_account、公式、分母定義、N/M rule，再寫 code。

### P2 — 需要補進 plan 的 guardrails

8. **Quick Ratio 的 input schema 尚不足**

   plan 用 `(cash+ST inv+AR) / CL`，但目前 SEC dictionary 有 `cash_and_cash_equivalents`、`accounts_receivable`，沒有 `short_term_investments` / `marketable_securities_current`。不能把缺項當 0，否則會低估 quick ratio。

   必修：
   - 要嘛先擴 parse-10QK-gaap + schema 抽短投 / marketable securities。
   - 要嘛 MVP quick ratio 定義為 `(cash + accounts_receivable) / current liabilities`，但名稱和公式要清楚標示，不可冒充標準 quick ratio。

9. **FCF formula 必須綁 SEC v2 sign convention**

   SEC parse 目前 `capital_expenditures` 來自 `PaymentsToAcquirePropertyPlantAndEquipment`，實際 JSON 值是正數 cash outflow；所以 SEC v2 的 FCF 應是 `net_cash_from_operating - capital_expenditures`。

   注意不要套用 TWSE legacy 的 `operating_cash_flow + capex` pattern，因 TWSE 那邊 capex 是負值。plan 應明寫 SEC v2 sign convention，並加測試。

10. **EBITDA / Adjusted EBITDA 的 GAAP/Non-GAAP 標示要更精準**

   `adjusted_ebitda` 已是 8-K Non-GAAP spotlight metric。若 derive-analytics 再用 add-back 自己 materialize adjusted EBITDA，會進入 Reg G reconciliation 領域，最好等 `sec_nongaap_adjustments` contract 存在再做。

   對 `ebitda`：
   - EBITDA 本身不是 GAAP measure，即使由 GAAP inputs 算出，也不要讓使用者誤讀為 filing GAAP line item。
   - 若存 `version='GAAP'`，需在 provenance / label 明確標示 `basis='GAAP_INPUTS_DERIVED_NON_GAAP_MEASURE'` 或等價欄位。
   - `operating_income + D&A` 是 operating EBITDA approximation；標準 EBITDA 通常從 net income 加 interest/tax/D&A。公式必須先定義，不可混稱。

11. **payload key / frontend row target 要泛化**

   目前 upsert 只讀 `{ticker}_analytics.json` 的 `ratio_metrics` key。若 derive-analytics 要輸出 FCF / EBITDA / Net Debt 這類 CF/IS/BS 絕對值，`ratio_metrics` 命名與 code contract 都會誤導。

   建議：
   - 新 schema 用 `analytics_metrics`，保留 `ratio_metrics` 讀取作 backward compatibility。
   - 前端 DoD 不應只寫 `RATIO_ROWS`；FCF 應進 `CF_ROWS`，EBITDA 可能進 `IS_ROWS` 或另設 analytics 區，Net Debt 可能進 BS/analytics 區。

12. **status section 已過期**

   §7 說 3 個前端 bug fix「尚未 commit」，但目前 repo 最新 commit 是 `3ed74f7 Financials Viewer: fix annual year-end BS mapping + effective tax rate N/M`。plan 需要更新，避免未來 session 誤判工作樹狀態。

---

## Claude 回應 Codex Review（質疑後判斷，2026-05-31）

> 沒有全盤接受。可查證的硬主張我實際查了 DB / JSON，屬實才採納；嚴重度分級有三處不同意，已降級。

### 查證結果（Codex 三個可驗主張，全部屬實）

| 主張 | 查證方式 | 結果 |
|---|---|---|
| P1.4 cell_id 是人類字串、無 formula、inputs 無 cell_id | 讀 `INTC_analytics.json` vs `INTC_derived.json` | ✅ 屬實：analytics=`derived::RATIO_...`、無 formula；derive-base=hash cell_id + formula/chained/target_table |
| P1.7 沒有 period-end shares | 查 Supabase `shares_*` rows | ✅ 屬實：只有 `quarter/ytd/fy_annual_duration`（加權平均），**無 instant_period_end**。BVPS 分母拿加權平均是錯的 |
| P2.9 SEC capex 為正、FCF 要相減 | 查 INTC `capital_expenditures` / `net_cash_from_operating` | ✅ 屬實：capex=+14646、CFO=+9697（都正）→ `FCF = CFO − capex`，不可套 TWSE 相加 pattern |

### 完全同意（採納）

- **P0.2 stale rows** — 機制確認：`managed_rule_ids` 從本次 emitted rows 反推，rule 產 0 row 時舊 Supabase row 不會被刪。derive-base 已用 owned-scope registry 解決，照抄。**真阻斷項。**
- **P1.4 的 cell_id + formula + input cell_id** — 查證屬實，且人類字串 cell_id 與全系統 hash identity 不一致。**必修。**
- **P1.5 FCF/EBITDA 不進 derive-base** — 邊界論證正確（derive-base = 填洞；FCF/EBITDA = 分析 KPI materialize）。**推翻本 plan 原本「傾向 derive-base」的寫法，改放 derive-analytics。**
- **P1.6 / P1.7 / P2.8 / P2.9 / P2.10 / P2.11** — 合理，採納（定義先進 schema 再寫 code）。

### 不同意 Codex 的嚴重度分級（降級）

1. **P0.1 不是 active bug，降為「擴展前護欄」** — 查 production **facts∩metrics RATIO 重疊 = 0**（LITE/AAOI/INTC/SNDK 全 0）。原因：facts RATIO 全是 NON_GAAP（8-K 揭露），metrics RATIO 全是 GAAP，version 不同永遠不撞 key。Codex 框成「會導致前端顯示錯值」是**對現狀誇大**；它只在「derive-analytics 開始算 NON_GAAP 比率」時才會真撞。→ 仍要加 facts-wins 護欄，但排在擴展前，不是修現有 breakage。
2. **P0.3 freshness gate 對現有 5-ratio MVP 價值低** — Codex 自承 additive 風險小。它是 EL1+（FCF/ROE）的前置，不是「現有 MVP 壞了」。降為擴展前置。
3. **P1.4 的 audit lineage 傳遞（has_audited_inputs / audited_input_cell_ids）列 fast-follow** — cell_id/formula 必修同意；但「ratio cell 要不要繼承 audit ✓ badge」是設計判斷，非 contract 正確性。margin cell 掛徽章可能反成視覺雜訊。不綁進 must-fix。

### Codex 漏掉的一點

- **YTD（6M/9M）orphan rows**：plan 提過、Codex 略過。決策：讓 analytics **從源頭不對 `ytd_duration` 期別算 ratio**，避免產生前端永不顯示的孤兒 row（除非未來要做 YTD view）。

### 收斂後的真正 Phase 0（取代原本「直接 Phase A」）

阻斷項（必須在任何新指標之前）：**P0.2 owned-scope 刪除** + **P1.4 cell_id/formula/input-cell_id 升級到 derive-base 同等 contract**。
擴展前護欄（Phase 0 一起做、但不是修現有 bug）：**P0.1 facts-wins** + **P0.3 freshness gate**。

---

## Codex Second-Pass Review（Claude 回應後，2026-05-31）

Claude 的查證大致成立：現有 derive-analytics output 只看到 GAAP rows，8-K direct ratios 走 facts，所以 P0.1 在「現有 production」不是 active overlap bug。不過這不改變 implementation 順序：facts-wins 仍必須在任何 Non-GAAP analytics 或 new ratio 前完成。

本輪剩餘必修點：

1. **Phase C 仍有舊矛盾，已修正**  
   前文已決定 FCF / EBITDA materialize 歸 `derive-analytics`，但原 Phase C 仍寫「在 derive-base 產 EBITDA / Adjusted EBITDA」。這會直接把 implementation 帶回錯邊界。Phase C 改成 `derive-analytics` 產 EBITDA；Adjusted EBITDA 不自行 add-back materialize，先只可用 8-K direct `adjusted_ebitda` 當 numerator。

2. **DoD 不能再只寫 `RATIO_ROWS` / `managed_rule_ids scope 清除`**  
   derive-analytics 擴展後會輸出 RATIO 以外的 CF / IS analytics metrics；DoD 必須要求「依 statement 對應到正確 frontend row group」，且 upsert 必須用 owned-scope registry snapshot replacement，而不是籠統寫 managed_rule_ids scope。

3. **Quick Ratio 不能用非標準公式但仍叫 `quick_ratio`**  
   若沒有 `short_term_investments` / marketable securities，`(cash + AR) / CL` 不應命名為 `quick_ratio`。兩個可接受選項：
   - 先擴 schema / parser 抽短投，再做標準 `quick_ratio`。
   - 或把 MVP 指標改名成 `cash_and_receivables_ratio` / `cash_ar_ratio`，並先進 `docs/sec-financials-v2-schema.md` 登記，不冒充 quick ratio。

4. **`analytics_metrics` 相容策略要明確**  
   upsert 若同時支援 `analytics_metrics` 與 legacy `ratio_metrics`，應規定優先順序：新 payload 以 `analytics_metrics` 為 canonical；`ratio_metrics` 只作 backward-compatible fallback。不要讓兩個 array 都被讀入造成 duplicate upsert / delete scope confusion。

5. **audit lineage fast-follow 可以接受，但 Phase 0 input helper 不要設計成丟失資訊**  
   即使 `has_audited_inputs` badge 是否顯示可晚點決定，Phase 0 在建立 input payload 時仍應保留 input provenance 中的 audit metadata，避免之後補 lineage 時又要重改 loader。

---

## 0. 前情提要（給 GPT / 未來 session 接手用）

### 0.1 系統是什麼

`AI_Agent` repo 的 **Financials Viewer**（Next.js App Router，`app/financials/[ticker]`）把 SEC XBRL 解析後的財報用表格 + 圖表呈現。資料分三類表：

- `sec_financial_facts` — 官方 XBRL / 8-K 直接揭露的**原始值**（IS / BS / CF / RATIO 直接揭露）
- `sec_financial_metrics` — **衍生值**（derived），由 derive skill 計算
- `sec_financial_dimensional_facts` — segment / geography 維度資料

### 0.2 既有的三層資料流（**這是本計畫必須遵守的不變量**）

```
┌── Skill 階段（在 Obsidian vault 本地產 JSON）──────────────────────────────┐
│  parse-10QK-gaap   →  {TICKER}_gaap.json / _gaap_facts.json   (source-of-truth)│
│  parse-8k-nongaap  →  {TICKER}_nongaap.json                                    │
│  parse-SEC-supplement → dimensional facts                                     │
│  derive-base       →  {TICKER}_derived.json   (Q4 重建 / IBT identity)         │
│  derive-analytics  →  {TICKER}_analytics.json (margins / ratios)               │
│                                                                               │
│  路徑慣例：<vault>/Khouse/Semiconductors/<TICKER>/01_Source/SEC Filings/       │
│            Skill_Output/<skill-name>/<YYYY-MM-DD-HHMM>/<TICKER>_*.json          │
│  （timestamp 到分鐘，一天可能跑多次；每個 run folder 獨立，保留歷史）          │
└───────────────────────────────────────────────────────────────────────────────┘
                          ↓ upsert（需明確 --apply 授權才寫 production）
┌── Supabase（前端真正讀的地方）─────────────────────────────────────────────┐
│  upsert_sec_financials.py：facts / metrics / dimensional / edges               │
│  metrics 用 managed_rule_ids scope 清除再寫（同一 skill 的 rule 重跑會先清舊）  │
└───────────────────────────────────────────────────────────────────────────────┘
                          ↓ /api/financials/[ticker]
┌── 前端 Financials Viewer（讀 Supabase，不讀本地 JSON）──────────────────────┐
└───────────────────────────────────────────────────────────────────────────────┘
```

### 0.3 三個必須守住的設計原則（用戶明確點名 + 記憶沿用）

1. **本地 JSON 一定要保留**。它不是中間產物，是：(a) audit artifact（可回溯）、(b) **Obsidian 內仍會用到的第一手顯示來源**（Obsidian 筆記 / Wiki / 圖表會直接讀這份 JSON）。→ 任何新指標都必須先落地成 JSON，再 upsert。**JSON 是第一種輸出顯示方式，Supabase 是給前端的第二落點。**
2. **前端資料在 Supabase**。前端不讀本地 JSON。所以新指標要顯示 = JSON → upsert → Supabase → API → 前端，全鏈打通才算數。
3. **Source-of-truth ONLY 紀律**：parse 階段**絕不算**衍生值；所有衍生（margins / Q4 / ROE / FCF…）只能在 derive-* skill 算，寫進 `sec_financial_metrics`，**不污染 `sec_financial_facts`**。每筆 derived row 帶 `provenance.formula` + `provenance.inputs`（回指來源 cell）+ `rule_id`。

### 0.4 derive-base vs derive-analytics 邊界

| | derive-base | derive-analytics |
|---|---|---|
| 目的 | 填洞（Q4 單季重建、IBT identity rollup、subtotal 補洞）| 算新指標（margins, ratios, 之後的 ROE/turnover…）|
| 輸出 statement | IS / BS / CF | **RATIO**（+ 未來可能新增絕對值衍生如 FCF/EBITDA）|
| 輸出 unit | USD_* / per_share | **Pure**（小數，前端 ×100 顯示 %）/ 倍數型顯示 x |
| 寫入表 | sec_financial_metrics | sec_financial_metrics |

### 0.5 目前 derive-analytics MVP 狀態（本計畫的起點）

- 引擎 `rules_ratios.py::compute_single_period_ratios`：對每個 `(period, version)` × 每條 rule，查單一分子 uni_account / 單一分母 uni_account，相除，擋 0 與缺值。
- 已上線 5 個單期比率：`gross_margin_pct` / `operating_margin_pct` / `net_margin_pct` / `effective_tax_rate` / `current_ratio`。
- 已對 LITE / AAOI / INTC / SNDK 跑完並 upsert。
- 前端 `RATIO_ROWS` 已預留 `ebitda_margin_pct` / `adjusted_ebitda_margin_pct` / `roe` / `roa` 的 row（目前顯示 `—`）。
- **本 session 剛修的 3 個前端 bug**（會在新計畫下重新驗證）：
  1. annual mode 把 `Q4_FYyyyy` instant cell 重映射成 `FYyyyy`（修好 BS annual 整片空白 + current_ratio annual 缺失）
  2. + 3. effective_tax_rate 在 `income_before_taxes ≤ 0` 時顯示 `N/M`（虛損期的稅率無意義）

---

## 1. 指標需求清單（NotebookLM 彙整 + 半導體核心）

> ⚠️ NotebookLM 誠實標註：流動性 / 效率 / 部分報酬率的「標準公式」來自外部財務知識，筆記本來源偏重 Non-GAAP / SEC Reg G / EBITDA / FCF。標準比率公式屬通用財務常識，採用前仍應人工確認分子/分母定義。

### 1.1 完整指標宇宙（按分類）

| 分類 | 指標 | 公式 | 單期 or 跨期 |
|---|---|---|---|
| 獲利 | Gross / Operating / Net Margin | profit ÷ revenue | 單期 ✅已有 |
| 獲利 | EBITDA Margin | EBITDA ÷ revenue | 單期（但需先有 EBITDA）|
| 獲利 | ROE | net_income ÷ **avg** total_equity | 跨期（平均餘額）|
| 獲利 | ROA | net_income ÷ **avg** total_assets | 跨期（平均餘額）|
| 獲利 | ROIC / ROCE | EBIT(1−t) ÷ invested_capital | 跨期 + EBIT |
| 流動 | Current Ratio | CA ÷ CL | 單期 ✅已有 |
| 流動 | Quick Ratio | (cash+ST inv+AR) ÷ CL | 單期（分子多科目）|
| 流動 | Cash Ratio | cash ÷ CL | 單期 |
| 槓桿 | Debt-to-Equity | total_liab(或 total_debt) ÷ total_equity | 單期 |
| 槓桿 | Interest Coverage | EBIT ÷ interest_exp | 單期 |
| 槓桿 | Net Debt / EBITDA | net_debt ÷ **TTM** EBITDA | 跨期 + EBITDA |
| 效率 | Asset / Inventory Turnover | rev或COGS ÷ **avg** balance | 跨期（平均餘額）|
| 效率 | DSO / DIO / DPO | (avg balance ÷ flow)×365 | 跨期 |
| 效率 | Cash Conversion Cycle | DIO+DSO−DPO | 跨期 |
| 成長 | Revenue / EPS YoY | (本期−去年同期)÷去年同期 | 跨期（去年同期）|
| 成長 | CAGR | (end/begin)^(1/n)−1 | 跨期 |
| 每股 | Book Value / Share | total_equity ÷ shares | 單期 |
| 每股 | Diluted / Adjusted EPS | net_income ÷ diluted_shares | 單期 or TTM |
| 現金 | FCF | CFO − capex | 單期（衍生**絕對值**，非比率）|
| 現金 | FCF Margin / Conversion | FCF ÷ revenue 或 ÷ net_income | 單期（需先有 FCF）|

### 1.2 半導體 / 科技硬體：分析師最看的核心 10（NotebookLM 點名）

| # | 指標 | 達成所需引擎能力 |
|---|---|---|
| 1 | Adjusted EBITDA / EBITDA Margin | EL3（EBITDA materialize）+ EL0 margin |
| 2 | FCF | EL1（衍生絕對值）|
| 3 | Adjusted EPS（Street）| 大致已有（8-K 直接揭露）|
| 4 | **Gross Margin** | ✅ EL0（唯一已完成）|
| 5 | Book-to-bill | EL3（XBRL 外，需新資料源）|
| 6 | Segment Operating Margin | EL3（dimensional_facts 管道）|
| 7 | Net Debt / EBITDA | EL2（TTM）+ EL3（EBITDA）|
| 8 | Adjusted ROCE | EL2（平均餘額）|
| 9 | Revenue YoY | EL2（去年同期）|
| 10 | Inventory Turnover / DIO | EL2（平均餘額）|

→ **核心 10 只有 1 個（gross margin）落在已完成的 EL0。真正的價值在 EL2（跨期引擎）+ EBITDA/FCF materialize。**

---

## 2. 引擎能力分級（Engine Levels, EL0–EL3）

> 為避免和記憶裡「pipeline Tier 1/2/3（source-of-truth / cross-check / derive）」混淆，這裡用 **EL（Engine Level）** 表示 derive-analytics 引擎本身的能力擴展層。

| Level | 能力 | 改動範圍 | 解鎖指標 |
|---|---|---|---|
| **EL0**（現況）| 單一 fact ÷ 單一 fact，同期 | 加 1 tuple + 前端 1 row | 5 個 margin/ratio ✅ |
| **EL1** | 分子/分母可為「多科目加減組合」+ 支援「衍生絕對值」（非比率，可寫 CF/IS statement、USD unit）| 引擎小幅擴充：rule 定義從 `(num_uni, den_uni)` 升級成可帶 expression；新增 absolute-value rule 類型 | Quick Ratio、Cash Ratio、D/E、Interest Coverage、Book Value/Share、**FCF**、FCF/OCF Margin |
| **EL2** | 跨期：TTM 加總 / 期初期末平均餘額 / 去年同期 lookup | **新引擎模組**（multi-period）：需要 period 拓撲（哪四季組成 TTM、哪期是去年同期、BS 期初=前一期期末）| ROE、ROA、ROIC、Asset/Inv Turnover、DSO/DIO/DPO、CCC、Revenue/EPS YoY、Net Debt/EBITDA（分母 TTM）|
| **EL3** | 上游新資料 / 新 materialize | 每個各自獨立工程 | EBITDA（derive-analytics materialize）、Adjusted EBITDA direct-source ratio（8-K direct numerator）、Segment Margin（dimensional 管道）、Book-to-bill（XBRL 外）|

---

## 3. 架構設計重點（每個 EL 要新增什麼）

### 3.1 EL1 — rule 定義升級 + 絕對值衍生

- **rule schema 升級**：現在 `SINGLE_PERIOD_RATIOS` 是 `(out_uni, num_uni, den_uni, stmt, rule_id)`。EL1 改成分子/分母可為「科目線性組合」，例如 quick assets = `+cash +short_term_investments +accounts_receivable`。
- **絕對值衍生 rule（新類型）**：FCF = `CFO − capex` 輸出的是 **USD 絕對值**，statement=CF，不是 Pure 比率。**歸屬已定（Codex P1.5 + 同意）：放 derive-analytics，不放 derive-base**（derive-base 邊界是「填洞」，FCF/EBITDA 是分析 KPI materialize）。payload key 從 `ratio_metrics` 泛化成 `analytics_metrics`（保留 `ratio_metrics` 讀取相容）。FCF sign convention：SEC v2 capex 為正 → `FCF = net_cash_from_operating − capital_expenditures`（**禁用** TWSE 的相加 pattern），且要加測試。
- 前端：margin 類照舊進 `RATIO_ROWS`，倍數型加進 `RATIO_AS_MULTIPLE`；**絕對值衍生（FCF）進 `CF_ROWS`、未來 EBITDA 進 `IS_ROWS` 或 analytics 區，不要全塞 `RATIO_ROWS`**（Codex P2.11）。

### 3.2 EL2 — 跨期引擎（最大投資）

需要一個共用的 **period 拓撲層**，一次設計好讓所有跨期指標共用：

- **TTM 加總**：給定一個 quarter，找出構成 TTM 的 4 季（含 Q4 用 derive-base 重建後的單季值）。注意：YTD（6M/9M）row 目前是 orphan，TTM 設計時要決定用 4 個單季加總還是用 YTD+前期還原。
- **平均餘額**：BS 是 instant，avg = (期初 + 期末)/2，期初 = 前一期期末快照。需要 period→前一期的映射。
- **去年同期**：`Qx_FYyyyy` → `Qx_FY(yyyy-1)`。
- **缺期處理**：跨期指標只要缺任一輸入期就 skip（跟 EL0 的 fail-closed 一致），前端顯示 `—` pending。
- 每個跨期 derived row 的 `provenance.inputs` 要列出**所有跨期輸入 cell**（含期別），維持可回溯。

### 3.3 EL3 — 上游 materialize

- **EBITDA**：= operating_income + D&A（operating EBITDA 近似）。**歸屬已定：放 derive-analytics（不放 derive-base）**。標示紀律（Codex P2.10）：EBITDA 不是 GAAP line item，即使由 GAAP inputs 算出，provenance/label 要標 `basis='GAAP_INPUTS_DERIVED_NON_GAAP_MEASURE'`；公式（OI+D&A 還是 NI+interest+tax+D&A）必須先在 schema 定義，不可混稱。
- **Adjusted EBITDA**：`adjusted_ebitda` 已是 8-K Non-GAAP spotlight metric。若 derive-analytics 自行 add-back materialize，會進 Reg G reconciliation 領域 — **等 `sec_nongaap_adjustments` contract 存在再做**，本計畫先不自算 adjusted EBITDA。
- **Segment margin**：走 `sec_financial_dimensional_facts`，跟主表不同 grain，需要獨立的 segment derive 路徑。
- **Book-to-bill**：XBRL 沒有，屬非財報 KPI，需另開資料源（暫不納入本計畫）。

---

## 4. 建議建置順序（Phase）

> 原則：先把現有 MVP 的 contract 補齊（Phase 0），再擴指標；跨期引擎一次設計到位再批次接。

- **Phase 0 — MVP contract 硬化（阻斷項，必須先做）**
  - **必修（修現有 debt）**：(a) row schema 升級到 derive-base 同等 contract — cell_id 改用 `metrics_cell_id()`、補 `provenance.formula`、inputs 帶 source `cell_id`（Codex P1.4）；(b) upsert 改用 **owned-scope rule registry** 做完整 snapshot replacement，不再從 emitted rows 反推 managed_rule_ids（Codex P0.2）。
  - **擴展前護欄（一起做，但非修現有 bug）**：(c) `filter_against_facts` facts-wins 防線 + 前端/API facts 優先（Codex P0.1，現狀 0 重疊）；(d) derive-analytics freshness gate（比對 input sha256，stale 預設 fail-closed，Codex P0.3）。
  - **YTD 處理**：analytics 不對 `ytd_duration` 期別算 ratio（消除 orphan row）。
  - DoD 補：facts+metrics 同 RATIO key 時前端顯示 facts 的 regression；stale-run regression。
  - audit lineage 傳遞（has_audited_inputs / audited_input_cell_ids）列 **fast-follow**，不卡 Phase 0。
- **Phase A — EL1 純單期擴充**：先只放「inputs 已存在、定義無歧義」者 → **Cash Ratio**（`cash_and_cash_equivalents / total_current_liabilities`）。Debt-to-Equity / Interest Coverage / Book Value per Share **先別動**，須先在 `docs/sec-financials-v2-schema.md` 登記定義（debt 定義、EBIT 定義、BVPS 需要 period-end shares 而我們只有加權平均 → 要先擴 parse 抽 instant shares，Codex P1.7）。
- **Phase B — EL1 組合分子 + FCF**：標準 Quick Ratio 需先擴 schema / parser 抽 `short_term_investments` / marketable securities；若短期先做 `(cash + AR) / CL`，指標名必須改成 `cash_and_receivables_ratio`（或等價明確名稱）並先進 `docs/sec-financials-v2-schema.md`，不可叫 `quick_ratio`。同 phase 做 FCF（絕對值衍生，歸 derive-analytics）+ FCF Margin / OCF Margin。
- **Phase C — EL3 EBITDA materialize**：在 derive-analytics 產 EBITDA（公式先在 schema 定義，且標示 `basis='GAAP_INPUTS_DERIVED_NON_GAAP_MEASURE'`），接上前端已預留的 EBITDA Margin row。Adjusted EBITDA 不自行 add-back materialize；只可用 8-K direct `adjusted_ebitda` 作為 numerator，完整 reconciliation 等 `sec_nongaap_adjustments` contract。
- **Phase D — EL2 跨期引擎**：一次把 period 拓撲層（TTM / avg-balance / YoY）建好，批次接上 ROE / ROA / Asset & Inventory Turnover / DSO·DIO·DPO·CCC / Revenue YoY / Net Debt/EBITDA。
- **Phase E — EL3 Segment margin**（選配）：dimensional 管道的 segment-level 利潤率。

每個 Phase 的 Definition of Done（沿用既有紀律）：
1. skill 產 JSON 到 Obsidian run folder（audit artifact + Obsidian 顯示）
2. upsert 到 Supabase（owned-scope rule registry snapshot replacement；不可只用 emitted rows 反推 delete scope）
3. 前端依 `statement` 對應到正確 row group（RATIO → `RATIO_ROWS`、FCF → `CF_ROWS`、EBITDA → `IS_ROWS` 或明確 analytics 區）與顯示格式，dev server 實測
4. regression test（沿用 derive-analytics / derive-base 既有 test 模式）
5. 更新 `docs/financials-*.md` + skill.md CHANGELOG

---

## 5. 合規禁區（NotebookLM / SEC 點名，務必遵守）

1. **🚫 FCF per share 禁止**：per-share 流動性指標違反 SEC ASR-142 / C&DI 102.05。**不要建 `fcf_per_share`**。
2. **Non-GAAP 比率的標示**：用 Non-GAAP 分子/分母算的比率（如 Non-GAAP operating margin、Net Debt/Adjusted EBITDA）本身就是 Non-GAAP financial measure，需可回溯到最接近的 GAAP 比較值（Reg S-K Item 10(e)）。我們的 `version='NON_GAAP'` 欄位要正確標。
3. **FCF 定義單一性**：SEC 認的 FCF = CFO − capex。任何額外 add-back 要改名 `adjusted_free_cash_flow`，不要混用。
4. **Segment 利潤率**：Topic 280 揭露的 segment 利潤本身不算 Non-GAAP，但拆出來的衍生 margin 要標清楚 grain。

---

## 6. 設計決策（含已決 / 待決）

**已決（Codex review + Claude 同意後定案）：**
- ~~FCF 歸屬~~ → **derive-analytics**（不放 derive-base），payload key 泛化 `analytics_metrics`。
- ~~EBITDA 歸屬~~ → **derive-analytics**；Adjusted EBITDA 等 `sec_nongaap_adjustments` contract 再做。
- ~~YTD orphan~~ → analytics 不對 `ytd_duration` 算 ratio。
- FCF sign → `CFO − capex`（SEC v2 capex 為正）。
- `analytics_metrics` 是新版 canonical payload key；`ratio_metrics` 只作 backward-compatible fallback。若兩者同時存在，upsert 讀 `analytics_metrics`，不可合併兩者。
- 標準 `quick_ratio` 不用缺項公式硬算；未抽短投前若要做 `(cash + AR) / CL`，必須使用不同 uni_account 名稱。

**仍待決（下一輪 GPT / 用戶拍板）：**
1. **TTM 的算法**：用 4 個單季（含 derive-base 重建的 Q4）加總，還是用 YTD + 前期還原？（YTD 不再產 ratio，但仍可作為 TTM 還原的中間料）
2. **TTM / 平均餘額的 storage/display contract（Codex P1.6）**：TTM ROE 等不是單季 duration、也不是 FY annual。要新增 `period_kind`（需 migration + 前端 filter）還是沿用 period label 但在 provenance 加 `window='TTM'` 並在 UI 標示？annual view 要顯示 FY annual ratio 還是 fiscal-year-end TTM ratio？**EL2 前必須先定。**
3. **平均餘額的 period 拓撲**：avg = (期初+期末)/2，期初取前一期期末。Q1 期初要不要跨年取前一年 Q4？單期不足時 fail-closed 還是退回 ending-balance 近似？
4. **N/M 邏輯是否推廣**：目前只有 ETR 做 `分母 ≤ 0 → N/M`。虧損期 ROE（權益可能為負）等要不要同樣處理？（傾向：抽成通用 helper，by-metric 設定分母正負規則）
5. **audit lineage 是否要傳到 ratio**：ratio 由 audited input 算出時，要不要繼承 ✓ badge？（Claude 傾向 fast-follow，非必要）
6. **JSON-first 下跨期 row 的輸出形狀**：跨期 `provenance.inputs` 很長（TTM 4 期 + 平均 2 期），JSON / Obsidian 顯示如何平衡可讀性 vs 完整回溯。

---

## 7. 本 session 已做、待新計畫定案後對齊的內容

- ✅ 對 AAOI / INTC / SNDK 跑 derive-analytics + upsert（production Supabase 已寫入）
- ✅ 3 個前端 bug fix（annual Q4→FY 重映射、ETR N/M ×2）— 已 dev server 實測通過，已 commit：`3ed74f7 Financials Viewer: fix annual year-end BS mapping + effective tax rate N/M`
- ⏳ 這些都會在新計畫的框架下重新檢視（特別是 N/M 是否推廣、annual 重映射是否要寫進 data-rules 文件）
