# Design v2: As Reported 重複行去重 — 整行冗餘 suppress（whole-row redundancy suppression）

Date: 2026-06-11 / Tier: T3 / Status: **design-converged**（3 證據 agent + 2 對抗設計 agent + 三方 review：Opus 4.8 / Fable 5 / Codex GPT-5.5 全部折回）
前身：v1（adapter per-cell suppress）被三方 review 否決 —— 見 §7 review 收斂紀錄。

## 1. 問題

As Reported（PDF-faithful）statement view 對同一條經濟線顯示重複行，當兩種 fact 並存：
- **prose fact**：source_account = PDF 文字，class=`preserved_pdf_label`（AGENT_CLASSIFIED 或 audited preserved）
- **tag fact**：source_account = XBRL concept 名，由 face_completeness（capture-everything）emit 進 `{section}_long_tail` bucket；class=`tag_like`

兩者都 display_eligible + 有 ordinal → coverage gate 100% 仍重複顯示。只有前端視覺驗收抓得到。

## 2. 證據（已驗證）

### 2.1 傷害範圍 = 只有 PDF 顯示層
derive-base deny `*_long_tail`（rules_q4.py:60）；derive-analytics 只吃 named core uni；無 footing 加總 long-tail；upsert cell_id 不同無衝突。uni 模式 `is_long_tail` 不在 IS_ROWS → 靜默丟（獨立 gap，§6 follow-up）。

### 2.2 受災戶 = SNDK + LITE（MU/INTC/AAOI 零 prose facts）
- **SNDK IS**（divestiture，兩邊 long-tail）：tag `GainLossOnSaleOfBusiness`(is_long_tail) vs prose(nonoperating_long_tail, AGENT_CLASSIFIED) 在 FY2025/Q1_FY2026/Q3_FY2025 重複；Q2_FY2025 **prose 唯一**（parse 視窗切掉 Q2 10-Q → edges_pre 無 Q2 edge → face_completeness P1.1 正確擋）。
- **LITE IS**（income_before_taxes，core vs long-tail）— 真實 pipeline ground truth：**24 對 display 重複**（prose core uni、ordinal 24；tag `IncomeLossAttributableToParent` is_long_tail、ordinal 22；24 對值全等）；12 YTD 期只有 tag（不顯示）；5 個 FY2020 季度只有 prose。

### 2.3 關鍵架構事實（決定整個設計，三方 review 證實）
**前端 render 的單位是 ROW（per-rowId 跨所有 period），不是 cell**（useFinancialMatrix.ts:403 prototype 建立、:475-479 Pass2 cell attach）。一個 row 只要**任一**顯示期有合格 prototype（`display_label != null || ordinal != null`，:148/:153）就存在；然後 Pass2 把**所有**同 rowId 的 cell 寫回該 row，**不檢查該 cell 自身 eligibility**。
→ **per-cell suppress 不可行**：被 suppress 的某期 cell 會經 Pass2 復活（只要該 rowId 在別期有唯一來源撐 prototype）。SNDK 'Gain on business divestiture' rowId 被 Q2（prose-only）撐住 → FY2025/Q3 的 suppressed cell 復活。
→ **只有「整行 suppress」安全**：把 loser 行**所有期** display_label+ordinal null 掉 → prototype 不建立 → 整行不 render → 無 cell 可復活。

### 2.4 持久化事實（Blocker 1，三方 review 證實）
`display_eligible` **非 DB 欄位**，upsert 前被 pop（upsert_sec_financials.py:743/725）；API 只回 display_label+ordinal（route.ts:96）。**唯一的顯示隱藏機制 = 持久化的 display_label 與 ordinal 皆 null**（前端 :153 OR 規則；T14 _maybe_exclude_note_level :782-784 正是 null 三者）。`display_eligible=False` 只供 adapter 內 coverage gate（_is_coverage_eligible :542），不影響顯示。

## 3. 設計：整行冗餘 suppress

**層級**：adapter dedup pass，在 `attach_display_to_batch` 跑完該 statement 的解析後執行。**前端零改動**（整行 null → 既有 prototype 邏輯自然隱藏）。不動 parse 邏輯（SNDK 需 re-parse 但只是視窗，非邏輯改動）。

### 3.1 Suppress 動作（解 Blocker 1）
對判定為 loser 的**整行**（該 rowId 的所有 period cell）：
- `row.display_label = None`、`row.ordinal = None`、`row.display_eligible = False`（後者只供 gate）
- `row.provenance += {display_exclusion_reason: "dedup_redundant_row", dedup_key: "A"|"B", dedup_winner_cell_id, dedup_winner_class}`
- loud log
Rollout = re-upsert in-place：cell_id 輸入欄位（ticker/period/period_kind/version/statement/uni_account/source_account/xbrl_tag，cell_id.py:43）**不變** → 同 PK 原地更新 display_label/ordinal 為 null。**不需 DELETE、不需 schema 改動**。

### 3.2 整行冗餘前提（解 Blocker 2 — 核心約束）
只有當 **loser 行的每一個「顯示期」（排除 period_kind=ytd_duration）都存在 winner 競爭者**時，才 suppress 整行。
- 任一顯示期無 winner → **fail-safe：不 suppress 整行**（寧可暫時重複，絕不讓某期值消失）+ WARNING（列入 dry-run 報告）。
- YTD 期：不納入「必須有 winner」判斷（YTD 不顯示），但 suppress 時一併 null（無副作用）。

### 3.3 配對 key（解 Blocker 3 + 範圍補強）
配對掃描範圍：同 `(statement, period, period_kind, version=='GAAP')`。

**Key A — long-tail vs long-tail（SNDK 類）**
prose 行 `resolve_via_label_text(source_account, edges, labels, statement)` → concept full-qname C（已 harden：face 顯示 role only、唯一 full-qname、否則 None）。同範圍存在 tag_like 行其 concept（full-qname，**非 bare local** — 解 namespace 碰撞）== C → tag 行為 winner 候選、prose 行為 loser 候選。
- **multi-occurrence veto**：同範圍有 >1 個 tag_like 行 concept==C → 不 suppress（fail-closed）。
- **CF instant 排除**：C 為 cash-balance / periodStart-End 概念（_is_cash_balance_concept）→ 不套用（CF cash movement 另有機制）。

**Key B — core vs long-tail（LITE 類）**
新增**獨立 registry**（**不碰 CANONICAL_CONCEPT**，避免污染 via_uni borrow 路徑）：
```python
# dedup ONLY. Concepts that denote the SAME economic line as a core uni_account,
# for whole-row redundancy suppression. NEVER used by resolve_via_uni*.
DEDUP_EQUIVALENT_CONCEPTS = {
    "income_before_taxes": {"IncomeLossAttributableToParent",
                            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest"},
}
```
tag_like 行為 `*_long_tail`、其 concept ∈ DEDUP_EQUIVALENT_CONCEPTS[U]、同範圍存在 uni==U 的 core 行 → core 行 winner、tag long-tail 行 loser。

**value-disagreement veto（兩 key 共用 — 一石二鳥）**
winner 與 loser 同期 **magnitude（|value|）** 不一致（abs 差 > tolerance）→ **不 suppress**（fail-closed）。
- 解 Codex Q3 反例（prose 被錯分類進錯 core uni → magnitude 不等 → veto 擋）。
- 解 Opus/Fable NCI-filer 反例（attributable-to-parent ≠ consolidated 差 NCI 份額 → magnitude 不等 → veto 擋；LITE 24 期值全等 → 正常 suppress）。
- **value 當「否決權」非「配對鍵」** —— 不違反 T3「禁止值配對靜默 bind」。
- **比 magnitude 非 signed display value（build pin，2026-06-11）**：原 v2 設計擬比「PDF-faithful 顯示值（含 negated）」，但真實 SNDK ground truth 推翻它 —— prose `'Gain on business divestiture'` 是 **pre-negated legacy data**（raw −34 且 display_negated=True → 顯示 +34），tag `GainLossOnSaleOfBusiness`（raw +34、display_negated=True → 顯示 −34 = (34)）。兩者代表**同一筆事件 |34|**，符號差異純粹是 negated-convention artifact，比 signed 顯示值會誤擋真重複。改比 |value|：符號從不承擔 identity（identity 已由 Key A label-text / Key B registry 的 concept 相等建立），value 只做 magnitude sanity 否決。NCI/錯分類 magnitude 不同仍擋。
  - 連帶釐清偏好序對 SNDK 的正確性：tag 顯示 (34)（negatedLabel 慣例，label `(Gain) loss on business divestiture` 帶括號）才是 PDF-faithful；prose 顯示 +34 是 legacy pre-negated bug。`tag > prose` 去掉顯示錯誤的 prose、留下正確的 tag，方向正確。

### 3.4 偏好序
`core uni 行 > tag_like long-tail 行 > prose long-tail 行`。理由：core = audited + 期別精確措辭（PDF-faithful 本體）；tag long-tail = XBRL 權威；prose long-tail（AGENT_CLASSIFIED）= legacy 自動分類、無不可替代措辭。**但偏好序只決定方向，suppress 與否仍受 §3.2 整行前提 + §3.3 三個 veto 把關。**

## 4. 兩案例落地

### SNDK（需先 re-parse）
1. **正確視窗 re-parse SNDK**（start-date ≤ Q2 10-Q filing 2025-03-07）→ capture-everything 抓 Q2 tag（companyfacts 90d=34M）→ tag 行涵蓋所有 prose 期。
2. Key A：兩個 prose rowId（'Gain on business divestiture'、'Loss on business divestiture'）每一顯示期都有 tag 競爭者（值相等：prose −34 = tag +34 經 negated 顯示相同）→ §3.2 滿足 → prose 整行 suppress。tag 行（display "(Gain) loss on business divestiture"）單行顯示。
   - 註：value-veto 比的是「PDF-faithful 顯示值」（含 negated）不是 raw value — 設計時用 winner/loser 各自 display 後的值比，或比 abs。**實作 TDD 要 pin 這個比法。**

### LITE（不需 re-parse）
Key B：tag 行（is_long_tail ATP）所有非 YTD 顯示期都有 prose core 競爭者、值全等 → tag 整行 suppress。prose core income_before_taxes 行保留（期別精確措辭、含 FY2020 prose-only 期）。
- **前置驗證（TDD/dry-run）**：確認 tag(ATP) 行的每個非 YTD 期都有 prose；若有缺口 → fail-safe 不 suppress（不會發生 LITE 重複殘留則接受暫不去重，記 WARNING）。

## 5. 驗收
- TDD（adapter）：Key A/B 觸發 + 三個 veto 不觸發 case（multi-occurrence、value-disagree、CF-instant）+ §3.2 整行前提（某期無 winner → 不 suppress）+ suppress 動作 null 兩欄。
- SNDK re-parse → dry-run：coverage 仍 100%、prose 整行不顯示、tag 單行全期。
- LITE dry-run：tag(ATP) 行整行 suppress、prose core 行全期保留、coverage 100%。
- **前端視覺驗收**（worktree dev server As Reported）：SNDK divestiture 單行、LITE income before taxes 單行措辭正確。
- 全 5 ticker regression（MU/INTC/AAOI 零 prose → 不觸發）。
- re-upsert LITE+SNDK 後 DB 驗證：loser cell 的 display_label/ordinal 確實為 null（解 Blocker 1 落地驗證）。

## 6. 不做 / Follow-up（進 ADR-005，不擋本次）
- ❌ per-cell suppress（前端 row model 不相容）；❌ 值當配對鍵；❌ ordinal 相等配對（證偽）；❌ 把 ATP 塞 CANONICAL_CONCEPT
- Follow-up：parse-window = 資料契約（LITE/SNDK/Q2 三案例，per-ticker 固定/自動推導 start-date + fail-loud）；face_completeness blank-source guard gap（源頭防新重複）；`is_long_tail` 不在 uni 字典（未來科目 Standardized 隱形）；resolver `_KW` 應信 persisted axis；BS/CF prose 目前零，未來若現需同 pass 覆蓋（pass 已 per-statement，加 BS/CF regression 斷言即可）

## 7. Review 收斂紀錄
- v1（per-cell adapter suppress + CANONICAL_CONCEPT 變體）→ 三方否決。
- **Blocker 1**（三方一致）：suppress no-op，必 null display_label+ordinal。
- **Blocker 2**（Fable 發現 cell 復活、Codex 拔高為「render row not cell」框架結論；Opus 漏）：→ 改「整行冗餘 suppress」+ fail-safe 前提，**繞過前端改動**。
- **Blocker 3**（三方一致，Codex Q3 反例最根本）：Key B 用獨立 registry；加 value-disagreement veto。
- 範圍補強（Fable 最全）：period_kind/version scope、CF-instant 排除、full-qname（非 bare-local）比對、multi-occurrence veto。
- 模型 review 比較：三方獨立收斂 Blocker 1（互證）；Fable 前端機制挖最深、Opus 修法穩健性最佳、Codex 證據鏈最深（API+schema 層）+ 框架洞見。互補性高。
