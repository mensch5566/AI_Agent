# Design — parse-SEC-supplement Stage-B-always（雙源直接抽取互相 cross-check 收斂）

Status: **DRAFT（待 user review → 雙模型 review → build）**
Date: 2026-06-12
Author: Claude (handoff draft)
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

- **容差**：只吸收 rounding（建議**相對容差 + 絕對下限**，如 `max(abs*0.001, 1)`，呼應「太嚴 vs 太鬆」—— 絕對 0 太嚴會被 rounding 觸發 false-positive）。容差**不是 derive**（只是比較門檻）。
- **period 權威**：用 filer 的 `dei:DocumentFiscalYearFocus` + `DocumentFiscalPeriodFocus` **直接讀**（已實作 `dei_period_label()`，52/53-週安全）—— 兩源都該對齊到 dei 宣告的財季，避免 SNDK 型 shift。
- **分類本身不可變成 derive**：只做「相等/不相等 + 缺一邊」的歸類，不算任何衍生量。

### §3.3 輸出
- `{T}_supplement_validation.md`（強化）：列出**所有 conflict（必看）** + xbrl_only/nlm_only 統計 + agree 統計。
- 收斂後的 canonical facts（per cell 標 cross-check 狀態於 provenance）。
- **gate**：有未解 conflict → 收尾報告明確標示（不阻塞抽取，但 ship 前人工要清）。

## §4 待 reviewer 定的開放點
- **Q1 容差數字 + 形狀**：相對 vs 絕對 vs 混合？不同 unit（thousands/millions/pct）門檻？
- **Q2 conflict 預設行為**：純報告等人工，還是給「XBRL 預設勝 + 標記」的暫態？（傾向純報告，T3 不靜默選邊）
- **Q3 cadence/成本**：每次 parse 都跑全 NLM，還是「新 filing 才跑該期」？user 說 NLM 不貴只慢一點 → 傾向每期都跑，但可加 cache（NLM 回應存 run folder，同 accession 不重查）。
- **Q4 sum-sanity（cross_check C）算不算 derive**：現有 `cross_check_supplement.py` C 做 `Σ(child·weight)=parent`。這是「驗 filer 自己 tag 的 parent vs children」（都直接讀），但涉及加總。**要 reviewer 裁決**：保留為 audit-only（不寫回值、純報告）是否可接受，或移除。
- **Q5 ticker_config**：Stage-B-always 需每個 ticker 有 NLM notebook + period_sources 設定。缺 config 的 ticker 怎麼 fail（fail-closed 提示補 config）。

## §5 Scope / Non-goals
- ✅ in: Stage B 永遠跑、XBRL↔NLM 直接抽取 cross-check 收斂、validation 報告強化、dei period 對齊。
- ❌ out（屬下游 derive/audit，不進 parse）：合理性邊界（算 margin/成長率設閾值）、segment 加總對合併、任何「算出新數字當驗證」。
- ❌ out: 改 XBRL 抽取本身（已是直接抽取）；改 schema（除非 provenance 加 cross-check 欄位）。

## §6 Build plan（T3 review-before-prod）
1. design spec（本文）→ user review → **雙模型 review（Opus 4.8 + GPT 5.5）收斂**。
2. TDD：cross-check 收斂 pass（合成雙源 fixture：agree / conflict / xbrl_only / nlm_only / 容差邊界）。
3. wire：extract_supplement_v3 always-chain Stage B + 收斂 pass + validation 報告。
4. 各 ticker 跑（work-profile NotebookLM；先 1 個 ticker 端到端證明，再全量）。
5. 人工清 conflict（real mismatch 修 raw NLM 或確認 XBRL）。
6. 收斂後 re-upsert（dimensional 快照替換已就緒）+ 前端驗證。

## §7 風險 / 注意
- NLM 幻覺：NLM 可能讀錯 → conflict 要人工判，不可自動信 NLM 覆蓋 XBRL。
- NLM 慢：全量跑耗時 → run-folder cache（同 accession 不重查）。
- work-profile 依賴：headless/cron 可能無 NLM auth（系統提示過）。
- 跨 ticker config 維護成本。
