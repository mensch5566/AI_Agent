# Design — parse-SEC-supplement Stage-B-always（雙源直接抽取互相 cross-check 收斂）

Status: **DESIGN-LOCKED（user 已拍板方向 2026-06-12；待雙模型 review → build）**
Date: 2026-06-12（v2 — 5 個開放決策已收斂進設計本體）
Author: Claude
Scope: `parse-SEC-supplement` skill（canonical `~/CC_Switch_Config/skills/parse-SEC-supplement/`）

---

## §1 問題（為什麼要改）

parse-SEC-supplement 目前是 **XBRL-primary + NLM-fallback（gap-triggered）**：

| Stage | 做什麼 | 觸發 |
|---|---|---|
| A — `parse_def_xml` + `parse_instance_xbrl` + `extract_supplement_v3` | 從 XBRL instance doc **直接抽** segment/geo/customer 維度值 → `{T}_supplement_facts_v3.json` + `coverage_gaps.json` | 永遠跑 |
| B — `extract_supplement`（NLM 讀 10-Q/10-K 原文）+ `cross_check_supplement` | NLM **直接讀**原文補值 → `{T}_supplement_facts.json` + cross_check.md | **只在 Stage A 有 coverage gap 時跑** |

**缺陷**：`coverage_gaps` 只抓得到「**漏抽（missing）**」，抓不到「**抽錯但有值（wrong-but-present）**」。

**實證（SNDK，2026-06-12）**：SNDK Q3_FY2026 的 segment op_income/revenue 值是對的（filer 真實揭露），但**期別標籤錯位**（52/53-週財曆 + 月份算術 + 缺 ticker_config → fy_end 預設 12，整批季別 shift 一季）。資料齊全、無 coverage gap → Stage B 不觸發 → 錯誤靜默上 production，最後是人工拿 flat GAAP 比對才發現。

→ 需要一個**對「抽錯但有值」也有效**的驗證機制。

## §2 原則（user 2026-06-12 拍板，鐵律）

- **parse skill 永不 derive**：parse-* 只從原文**直接拿值**，不加總、不算比率、不反推、不用月份算術推季別。derive 是 derive-base/derive-analytics 的事。
- 因此驗證**不可用 derive 當手段**：❌「把 segment 加總比合併」「算營業利益率設合理性邊界」這些是 derive，不能進 parse 的驗證層（要做放下游 derive/audit 層）。
- ✅ 正解 = **雙源「直接抽取」互相 cross-check**：XBRL instance（filer tag 的值）與 NLM 讀原文（同文件印出的值）都是「filer 揭露了什麼」的直接讀取，只是兩條路徑。比對兩者 = **純驗證、零 derive**。

## §3 設計：Stage-B-always

### §3.1 流程變更
- Stage A（XBRL）**和** Stage B（NLM）**都永遠跑**（不再 gap-triggered）。
- 兩者各自產出**獨立的直接抽取結果**：
  - `{T}_supplement_facts_v3.json`（XBRL-primary，現有）
  - `{T}_supplement_facts.json`（NLM-derived，現有）
- 新增/強化 **XBRL↔NLM cross-check 收斂** pass：per `(period, axis, member, uni_account)` 比對兩源。

### §3.2 cross-check 收斂規則（per cell）
| 情況 | 判定 | 動作 |
|---|---|---|
| 兩源都有、值一致（容差內）| ✅ confident | 採 XBRL（primary）；provenance 記 `cross_checked: true` |
| 兩源都有、值不一致（超容差）| ❌ conflict | **flag 進 must-review 報告**，不靜默選邊；人工裁決後固化 |
| 只有 XBRL | ⚠ xbrl_only | 採 XBRL；標 `nlm_unconfirmed`（NLM 沒讀到，可能 NLM 漏或 prompt 不到位）|
| 只有 NLM | ⚠ nlm_only | 採 NLM（XBRL 無此維度，如小公司沒打 segment XBRL tag）；標 `xbrl_missing` |

- **容差（決議 D1）**：`tol = max(abs(xbrl) * REL, FLOOR[unit_class])`，只吸收 rounding。
  - `REL = 0.005`（0.5%）—— XBRL 是精確值、NLM 讀 PDF 是 filer 印出的同一數字，真實差異只該來自 PDF 顯示位數的進位。
  - `FLOOR`（per unit-class，半個顯示精度單位）：`USD_millions → 1`、`USD_thousands → 1`、`pct → 0.1`（即 0.1 個百分點）。
  - 絕對 0 太嚴（rounding false-positive），純相對對小值太鬆 → 取兩者 max。容差**不是 derive**（只是比較門檻）。
- **period 權威**：用 filer 的 `dei:DocumentFiscalYearFocus` + `DocumentFiscalPeriodFocus` **直接讀**（已實作 `dei_period_label()`，52/53-週安全）—— 兩源都該對齊到 dei 宣告的財季，避免 SNDK 型 shift。
- **分類本身不可變成 derive**：只做「相等/不相等 + 缺一邊」的歸類，不算任何衍生量。

### §3.3 輸出
- `{T}_supplement_validation.md`（強化）：列出**所有 conflict（必看）** + xbrl_only/nlm_only 統計 + agree 統計。
- 收斂後的 canonical facts（per cell 標 cross-check 狀態於 provenance）。
- **gate**：有未解 conflict → 收尾報告明確標示（不阻塞抽取，但 ship 前人工要清）。

## §4 決議（user 2026-06-12 拍板，原開放點已收斂）

- **D1 容差形狀** → 見 §3.2：`max(abs*0.5%, FLOOR[unit])`，FLOOR=`{millions:1, thousands:1, pct:0.1}`。
- **D2 conflict 預設行為** → **純報告等人工**。conflict cell **不靜默選邊**（不給「XBRL 暫態勝」），一律進 must-review 報告由人裁決後固化。T3 紀律：silent auto-pick 是 SNDK 型 silent error 的溫床，禁止。
- **D3 cadence / 成本** → **每期都跑 NLM**（user：NLM 不貴只慢）。加 **run-folder cache，key = accession number**：同一份 filing（同 accession）已查過就讀 cache，不重打 NLM。新 filing 才實際 query。→ 兼顧「全期都驗」與「不浪費」。
- **D4 sum-sanity（現有 cross_check C `Σ(child·weight)=parent`）** → **降級為 audit-only 加分項**。
  - 主驗證 = §3.2 的 **XBRL↔NLM 雙源直接抽取 cross-check（零 derive）**，sum-sanity **不是**主驗證手段。
  - sum-sanity 涉及加總（technically derive），依鐵律「parse 內真要 derive 也只能是加分項，絕不能是主要手段或驗證手段」→ 保留為 **純報告 audit 訊號**：**永不寫回值、永不選邊、永不據以改 canonical**，只在 validation.md 印一行 advisory（「filer 自報 parent vs Σchildren 對不上」），給人看。
  - 它驗的是 filer **自己 tag 的** parent vs children（兩邊都直接讀），不是我們算出新數字塞回去 → 在「加分項、不寫回」的框內可保留。
- **D5 ticker_config 缺漏** → **fail-closed**。Stage-B-always 需每 ticker 有 NLM notebook + period_sources。缺 config → **明確報錯停下**（「ticker X 缺 NLM config，無法雙源驗證，請補 ticker_configs/X.json」），**不可靜默退回 XBRL-only**（那正是現在 SNDK 型盲區，退回等於白改）。

## §5 Scope / Non-goals
- ✅ in: Stage B 永遠跑、XBRL↔NLM 直接抽取 cross-check 收斂、validation 報告強化、dei period 對齊。
- ❌ out（屬下游 derive/audit，不進 parse）：合理性邊界（算 margin/成長率設閾值）、segment 加總對合併、任何「算出新數字當驗證」。
- ❌ out: 改 XBRL 抽取本身（已是直接抽取）；改 schema（除非 provenance 加 cross-check 欄位）。

## §6 Build plan（T3 review-before-prod）
1. ~~design spec（本文）→ user review~~（✅ done，方向已拍板）→ **雙模型 review（Opus 4.8 + GPT 5.5）收斂**（下個 session 起手）。
2. TDD：cross-check 收斂 pass（合成雙源 fixture：agree / conflict / xbrl_only / nlm_only / 容差邊界 D1 / pct vs millions FLOOR）。
3. wire：extract_supplement_v3 always-chain Stage B + 收斂 pass + accession-keyed cache（D3）+ validation 報告（含 sum-sanity advisory 行 D4）。
4. fail-closed config gate（D5）：缺 ticker_config → 報錯停。
5. 各 ticker 跑（work-profile NotebookLM；先 1 個 ticker 端到端證明，再全量）。
6. 人工清 conflict（real mismatch 修 raw NLM 或確認 XBRL）。
7. 收斂後 re-upsert（dimensional 快照替換已就緒）+ 前端驗證。

## §7 風險 / 注意
- NLM 幻覺：NLM 可能讀錯 → conflict 要人工判，不可自動信 NLM 覆蓋 XBRL。
- NLM 慢：全量跑耗時 → run-folder cache（同 accession 不重查）。
- work-profile 依賴：headless/cron 可能無 NLM auth（系統提示過）。
- 跨 ticker config 維護成本。
