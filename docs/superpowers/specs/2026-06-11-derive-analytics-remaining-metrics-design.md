# Design — derive-analytics 收尾指標：BVPS / Adjusted-EBITDA-Margin / Segment-Operating-Margin

Date: 2026-06-11 / Tier: T3 / Status: **design — 待 Opus 4.8 + GPT 5.5 收斂**
目標（/goal）：把分析師核心 10 裡剩下可做的補完，每項走完整 T3 SOP + 雙模型收斂 + 前後端驗證。

## 0. 範圍與 triage（已查 production 資料）
核心 10 已上線 7：FCF / Gross Margin / Net-Debt-EBITDA / ROIC(≈Adj ROCE) / Revenue YoY / DIO-turnover / 普通 EBITDA。剩 4：
- **#6 Segment Operating Margin** — 可做（INTC+MU 有 segment revenue+operating_income，business_segment 軸；LITE 只 revenue、SNDK 稀疏）。
- **#1 Adjusted EBITDA / Margin** — `adjusted_ebitda` 已是 NON_GAAP fact（11 rows，8-K direct）；缺 margin 衍生 + surfacing。
- **#3 Adjusted EPS** — 已是 `eps_diluted` NON_GAAP（68 rows），走 Non-GAAP spotlight。**疑已具備，僅需確認 surfacing**。
- **#5 Book-to-bill** — **out of scope**：需訂單/bookings 資料，XBRL 完全沒有。文件記錄為不可做，未來若接外部訂單源再議。
- **BVPS**（非核心10但 roadmap 長期掛著）— 期末股數 `CommonStockSharesOutstanding`（instant，全5 ticker）已 parse 進 `bs_long_tail`。先前「只有加權平均」結論**過時**。可做。

## 1. BVPS（book value per share）
**公式**：`bvps = common_equity / shares_outstanding`（皆 BS instant、同期 → EL1 單期 pattern，類 current_ratio）。
**輸入決策**：
- `shares_outstanding`：把 `CommonStockSharesOutstanding`（period-end instant）從 `bs_long_tail` **升格為 core uni**（parse BS tag map 加 `shares_outstanding`）→ re-parse 5 ticker。理由：期末流通股數是正當 core 指標（BVPS 以外也有用），符合「不寫 hack、core uni only」紀律；不走「rule 直讀 bs_long_tail by source_account」hack。
- **common_equity 取值（開放Q1）**：BVPS(common) = 普通股東權益 ÷ 普通股數。我們有 `total_equity`（可能含 NCI / preferred）。**提案**：numerator 用 `total_equity − preferred_equity(optional 0) − noncontrolling_interest(optional 0)`；5 ticker 多為 common-only（optional 缺則 0），preferred/NCI 有揭露才扣。請 reviewer 確認 attributable-to-parent 取法。
**單位**：`USD_per_share`（前端 `per_share` group 已存在，EPS 用）。需引擎 `output_unit` 支援 per-share（equity $M ÷ shares M = $/share，量級自洽）。
**skip policy**：`shares_outstanding ≤ 0` → skip（denom nonpositive）；負 book value 允許（BVPS 可負，有意義）。
**rule_id**：`RATIO_BVPS`。**統計**：每 ticker 看 shares 覆蓋（LITE 27/MU 22/AAOI 13/INTC 3/SNDK 3）。
**前端**：BS 區或 ratios 加 `bvps` row，per-share 格式。

## 2. Adjusted EBITDA Margin（+ 確認 Adjusted EPS surfacing）
**公式**：`adjusted_ebitda_margin_pct = adjusted_ebitda(NON_GAAP) / revenue`。
**輸入決策（開放Q2）**：分子 `adjusted_ebitda` 是 **NON_GAAP** version fact；分母 revenue 用 **GAAP**（Adj EBITDA margin 慣例分母同 GAAP revenue；NON_GAAP revenue 通常等於 GAAP）。EL1 `Term` 目前無 `version` 欄、預設吃 rule 的 version context → **需加 `Term.version`（None=沿用 rule version；明確指定可跨 version）**。請 reviewer 確認跨-version term 的污染風險（會不會誤吃到別 version 的同 uni）。
**adjusted_ebitda 本身 surfacing**：它已是 NON_GAAP fact；確認前端 Non-GAAP spotlight / IS 是否顯示（不顯示則補）。
**Adjusted EPS**：已是 `eps_diluted`@NON_GAAP，確認 Non-GAAP spotlight 顯示即可，**無新衍生**。
**rule_id**：`RATIO_ADJUSTED_EBITDA_MARGIN_PCT`，basis 標 `GAAP_INPUTS...`? 否 —— adjusted_ebitda 本身是 management NON_GAAP 揭露值，不是 GAAP-derived，basis 應標來源為 8-K direct。請 reviewer 定 basis 標記。

## 3. Segment Operating Margin（EL3 dimensional — 最大）
**公式**：`segment_operating_margin_pct = segment.operating_income / segment.revenue`，per (ticker, business_segment, period)。
**新輸入路徑（開放Q3）**：derive-analytics 目前**不讀 dimensional facts**。segment revenue/op_income 在 `parse-SEC-supplement/{T}_supplement_facts.json`（DB `sec_financial_dimensional_facts`，axis=business_segment）。需新 loader 讀 supplement 維度 facts。
**輸出目標（開放Q4）**：per-segment 衍生 margin 要存哪？選項：(a) 寫回 `sec_financial_dimensional_facts`（axis=business_segment, uni_account=operating_margin_pct, 標 derived）；(b) 新 metrics 表。**提案 (a)**：跟 segment 原始值同表同軸，前端 SegmentTable 已讀該表，surfacing 最自然；用 status/source 標 derived 隔離。請 reviewer 定。
**skip policy**：segment 缺 operating_income 或 revenue≤0 → skip（fail-closed）。LITE（只 revenue）→ 全 skip；SNDK 稀疏 → 少量。INTC+MU 完整。
**period 對齊**：segment facts 的 period_kind（single_quarter / fy_annual / cumulative_ytd）；margin 只在 revenue 與 op_income 同 period+period_kind 都在時算。
**前端**：SegmentTable 加 operating margin 行/欄（per segment per period）。

## 4. 不做（記錄）
- **Book-to-bill**：XBRL 無 bookings/orders 資料，不可從現有管道算，**不做**；未來若有訂單資料源（IR deck / 自建）再開。

## 5. 共同 SOP 紀律
每項：TDD 紅→綠 + property test（守衛）；canonical SSOT + 4 mirror sync；dry-run diff（既有值不動）；**Opus 4.8 + GPT 5.5 雙模型對抗 review 收斂**；production `--apply` 需 user 授權；前後端驗證（dev server）；STATUS + skill CHANGELOG。
**建議順序**：BVPS（最乾淨、資料確認）→ Adjusted EBITDA Margin（小）→ Segment Operating Margin（最大、新路徑）→ 品質殘留（net_debt review / AAOI NLM 查證 / P3）。

## 6b. v2 收斂（Opus 4.8 + GPT 5.5 雙模型，2026-06-11）— 定案修正
兩方獨立 BUILD-WITH-CHANGES，收斂如下（取代上方有衝突處）：

**BVPS（建第二）**
- numerator = `total_equity` **原樣**（= `StockholdersEquity`，xbrl_extract:513-515 確認已是 parent-only / NCI 另存 `minority_interest_bs`）。**絕不扣 NCI**（否則 INTC 雙扣 −7%，已驗）。preferred 只在有「已 parse 的 preferred_equity core key」時才扣，**不 silent-zero**（目前無 → 不扣）。修正 `rules_crossperiod.py:13` 的錯註解。
- shares 對齊既有 checklist key **`shares_outstanding_filing_date`**（core-checklist:254，point-in-time），**不另造 `shares_outstanding`**；把 `CommonStockSharesOutstanding`(instant) 升格映此 core key（parse BS tag map）→ re-parse 5 ticker。
- **per-share 單位代數（新引擎能力）**：ratio path 目前硬寫 `output_unit=Pure`（rules_ratios:331-341）。加：`USD_millions / millions_shares → USD_per_share`、`USD_thousands / thousands_shares → USD_per_share`；**scale 不一致（如 AAOI equity=USD_thousands、shares=millions）必先 rescale 對齊，否則 fail-closed**（裸除錯 1000×，已驗 AAOI $5,938 vs 真值 $5.94）。
- skip `shares ≤ 0`；負 book value 允許。

**Adjusted EBITDA Margin（建第一，最小）**
- `adjusted_ebitda_margin_pct` routing(adapter:65)+前端 label(constants:138) **已存在** → 只需引擎 emit。
- 引擎加 `Term.version`（None=沿用 cell version）+ rule 級 `output_version="NON_GAAP"` + `allow_cross_version=True`。numerator `adjusted_ebitda@NON_GAAP` / denominator `revenue@GAAP`。
- **防重複 emit**：cross-version rule 只在 `cell.version == rule.output_version` 那輪 emit（否則 GAAP+NON_GAAP 兩輪各 emit 一次）。
- **provenance.inputs 要記每個 input 的 version**（目前漏，rules_ratios:368-374）—— 跨 version 後必要。
- basis 用新 marker `MGMT_NONGAAP_INPUT_DERIVED_RATIO`（**不是** `GAAP_INPUTS_DERIVED_NON_GAAP_MEASURE`；adjusted_ebitda 是 management 8-K 揭露非 GAAP-derived）。
- coverage 誠實：**AAOI-only**（11 rows），Q4 看 GAAP revenue period_kind 對齊。

**Segment Operating Margin（建第三，最大）**
- 輸入 = **`{T}_supplement_facts_v3.json`**（非 `_supplement_facts.json`，後者不存在）。
- 新 loader：`unit:"usd"`、period_kind normalize（`single_quarter→quarter_duration` / `fy_annual→fy_annual_duration`）、`version:None→"GAAP"`、member 配對用 `source_account_qname` / `member_key`。排除 `cumulative_ytd`。
- 配對 key：`(ticker, axis_key, member_key, period, period_kind)` 完全一致才算；`revenue ≤ 0` 或缺 op_income → skip（LITE 只 revenue 全 skip）。
- **輸出（兩方略有分歧，定案）**：寫回 `sec_financial_dimensional_facts`（dimensional_cell_id + API 讀路徑已存在，cell_id:97-125 / route.ts:116-124），但**走獨立 `derive_dimensional_analytics` 路徑** + `provenance.derived=true` + `provenance.rule_id/formula/inputs`；schema 先把 `operating_margin_pct` 加進 dimensional allowed keys（schema:380-388）。注意：DB dimensional 表**無 status 欄**（migration:123-145）→ 用 provenance.derived 區隔，delete-scope 用 rule_id 管理（不可混進既有 segment 原始值的 upsert scope）。**最重要風險（Codex）**：別把 segment margin 硬塞既有 derive-analytics metrics pipeline（grain/identity/delete-scope/前端路徑全不同 → 靜默 stale-row / 寫錯表）。

**Book-to-bill**：兩方一致 **DO NOT BUILD**（XBRL 無 bookings/orders）。
**順序定案**：Adjusted EBITDA Margin → BVPS → Segment Operating Margin。每項 TDD + property test + dry-run + 雙模型 code review + production 授權 + 前後端驗證。

## 6. 給 reviewer 的關鍵問題
- Q1 BVPS common_equity 取法（total_equity − preferred − NCI optional？attributable-to-parent？）+ per-share 單位處理是否乾淨。
- Q2 `Term.version` 跨-version 解析的污染風險 + Adj EBITDA margin 分母用 GAAP revenue 是否正確。
- Q3/Q4 segment 衍生的輸入 loader + 輸出表選擇（寫回 dimensional_facts vs 新表）。
- 有無更該優先 / 更該砍的項目？順序合理嗎？

---

## §7 Segment Operating Margin — BUILD 進度 + 架構決策（2026-06-11）

### ✅ 已完成（commit `886bb39` canonical）
- 引擎 `rules_dimensional.py::compute_segment_operating_margin`（10 test）：per (period, period_kind, business_segment member, GAAP/Non-GAAP type) 配對 revenue↔operating_income，pairing key 含 `source_account_qname` + `other_dimensions`（list-of-{axis,member}）→ consolidation context 不交叉。fail-closed：缺 op_income 或 revenue≤0 skip。負 margin emit。
- 真實驗證：INTC 15 / MU 22 / SNDK 1 / LITE 0 margins。值合理（Intel Foundry -57.9% 配 total revenue 含 intersegment 正確、MU SBU FY2023 -73.9% 記憶體寒冬）。

### ⚠️ BUILD 關鍵發現（resume 必讀）
1. **normalize_pct_value 腐蝕陷阱**：`_adapt_one_supplement_fact` 對 Pure unit 走 `normalize_pct_value`，會把 `abs>1` 的值除以 100（當百分點）。segment margin 可 **<-100%**（小營收大虧損 segment）→ 會被腐蝕成 1/100。目前真實資料 0 筆 |margin|>1（潛在風險），但 T3 必須避開：**segment margin 的 DimensionalRow 要直接建、存原始 fraction、unit="Pure"、不走 normalize_pct_value**（與 flat operating_margin_pct 一致，後者也不走）。需 TDD 一個 >100% case 鎖住。
2. **flat vs dimensional `operating_margin_pct` 同名**：`RATIO_UNI_ACCOUNTS` 已有 flat `operating_margin_pct`（sec_financial_metrics）。segment 版同名但在 `sec_financial_dimensional_facts`（不同表、不同 cell_id grain：含 axis_key/member_key）→ 不碰撞，但 routing/前端要分清。

### 架構決策（定案）
- **computation 在 canonical skill**（rules_dimensional.py），**upsert 在 AI_Agent**，兩者不互 import（io_loader 已是 AI_Agent→skill 反向 import 的特例，不再加耦合）。
- **照設計「獨立 derive_dimensional_analytics 路徑」**：derive 端（新 `derive_dimensional_analytics.py` 或 derive_analytics.py 擴充）讀 `{T}_supplement_facts_v3.json` → 算 segment margins → 寫 `{T}_dimensional_analytics.json`。upsert 新增 discovery + `adapt_dimensional_analytics_facts`（在 sec_json_adapter.py，**直接建 DimensionalRow 不走 normalize_pct_value**）→ batch.dimensional。
- **cell_id**：`dimensional_cell_id(ticker, period, normalize_supplement_period_kind(kind), axis_key, member_key, uni_account="operating_margin_pct", other_dimensions)` → 與 raw segment rev/oi row 不同 cell_id（uni_account 不同）。
- **delete-scope（Codex 最大風險）**：dimensional 目前是純 upsert-by-cell_id（無 status 欄、無 clear）。derived margin 也走純 upsert（cell_id 穩定、re-run 覆蓋）。**絕不可**把 derived margin 混進 raw segment 的任何 clear scope。用 `provenance.derived=true` + `provenance.rule_id=DIM_SEGMENT_OPERATING_MARGIN_PCT` 標記，未來若加 dimensional clear-scope 要按 rule_id 分。
- **schema**：`operating_margin_pct` 需在 dimensional allowed uni_accounts（確認 migration/schema 是否已允許；DB 已有 revenue_pct_of_total 等 pct dimensional key，存 decimal unit="Pure"）。
- **前端**：SegmentTable 加 operating margin 行/欄（per segment per period），讀 dimensional API（route.ts 已存在）。
- **SNDK 單一 segment**：「Reportable Segment」margin = 合併營業利益率，與 flat 重複且 69.1% 偏高疑似 supplement op_income 誤標 → 上游 supplement 資料待查（非引擎 bug）。考慮：單一 reportable segment 是否值得 emit（可能該 skip 或前端不顯示重複）。

### 剩餘步驟
derive_dimensional_analytics.py（讀 v3 + compute + 寫 JSON）→ adapt_dimensional_analytics_facts（TDD，含 >100% no-corruption case）→ wire upsert discovery + batch.dimensional → schema allow key → 前端 SegmentTable → 雙模型 review → production 授權 → 前後端驗證。

### §7.1 雙模型 review round-1 BLOCKERS + 修復（2026-06-11，commit `3fd2fea`）
兩個模型（Opus 4.8 + GPT 5.5）都抓到 2 個 T3-fatal blocker：
1. **null-qname member collapse**：`_pair_key` 只用 `source_account_qname`，但 MU 的 225 個 segment facts qname **全 null** → 同期所有 member collapse 成一個 bucket key（None）→ last-write-wins 掉 88/110 MU margin，且可能拿 member A 的 op_income ÷ member B 的 revenue 捏造數字。INTC/SNDK/LITE qname 非 null 故沒事（盲點）。
   **修**：新 `_member_id(f) = source_account_qname or source_account`（label fallback）；`_pair_key` 改用它。value-conflict guard：同 (member,period,kind,uni) 兩個不同值 → 該 pair_key 標 conflicted 跳過（不 last-write-wins、不捏造）。
2. **SNDK 單一 reportable segment 假 margin**：Q2_FY2026 op_income $4.111B/rev $5.95B=69.1%，但 SNDK 合併 op margin ~8% → 上游 supplement op_income 誤標。
   **修**：ticker 的 business_segment 只有 ≤1 distinct member → suppress 全部（非真實 disaggregation、與 flat consolidated 重複）。
**驗證**：MU 22→110 margins（FY2021 全 5 member）、SNDK 1→0、INTC 15 不變、LITE 0。12 dimensional test。

### §7.2 待辦（上游）：SNDK supplement Q2_FY2026 segment 資料疑誤
SNDK Q2_FY2026 segment revenue $5.95B（平常 ~$2.3B）+ op_income $4.111B 兩值都不合理（疑 parse-SEC-supplement 抽到錯 XBRL concept 或 cumulative）。已由 single-member suppress 擋住不進 production，但**上游資料本身要修**（re-parse SNDK supplement v3 Q2_FY2026，比對 10-Q 原文）。

### §7.3 SNDK 資料疑慮 — 查證結案（2026-06-11，已修上 production）
**結論：op_income 4111M / rev 5950M（69% 營業利益率）是 filer 真實揭露，不是抽錯。** IS 完整對帳：Revenue 5950 − COGS 1288 = GrossProfit 4662（78%）− OpEx 551 = OperatingIncome 4111（69%）→ NetIncome 3615（61%）。SanDisk 記憶體超級循環 + FY2025 提列存貨在缺貨高價賣出（writedown reversal）→ 極端毛利。parse 忠實抽出。
**唯一真 bug = 期別標籤錯位**：`parse_instance_xbrl` 用月份算術 + fy_end（SNDK 缺 ticker_config → 預設 12）撐不住 52/53 週財曆，整批季別 shift（2026-04-03 被標 Q2_FY2026 應為 Q3_FY2026）。
**修法（已上）**：(1) `dei_period_label()` 改用 filer 的 DocumentFiscalYearFocus + DocumentFiscalPeriodFocus（權威、52/53 週安全），commit parse-SEC-supplement；(2) upsert dimensional 改 per-ticker 快照替換（清孤兒），commit `13e9667`。SNDK re-parse + re-upsert（user 授權）：60→60 無孤兒，business_segment 季別 FY2025/Q1-Q3_FY2026 全對。
**啟示（呼應「太嚴 vs 太鬆」）**：period label 應優先用 filer 權威來源（dei focus）而非推算；dimensional 應跟 flat 一樣對「可靠來源」snapshot，避免靜默孤兒。
