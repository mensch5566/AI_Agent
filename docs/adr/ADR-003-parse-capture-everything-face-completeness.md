---
type: adr
id: ADR-003
status: accepted
tier: T3
created: 2026-06-06
supersedes: none
related: docs/adr/ADR-002-bs-long-tail-catch-all.md
---

# ADR-003：parse-10QK-gaap capture-everything — presentation-linkbase face-completeness pass

> 格式：Context / Decision / Alternatives / Consequences（對齊 ADR-001/002）。
> 狀態：**accepted**（GPT-5.5 xhigh Codex 4 輪 review 收斂 → SAFE TO MERGE；獨立 subagent 對抗審查；42 tests + 5-ticker e2e all-green；人類核可併回 SoT 2026-06-06）。
> 設計細節見 dev workspace `tmp/parse-10QK-gaap-dev/DESIGN-capture-everything.md` 與 `CODEX-REVIEW-round1..4.md`。

## Context

ADR-002 補了 BS long-tail（②類無核心歸屬科目進 bucket），但 allowlist extractor（IS/BS/CF_TAG_MAP, first-match-wins）的根本特性沒變：**任何不在 tag map 的 concept 直接丟掉**。實務後果——PDF 三表面上明明有、companyfacts API 也拿得到的科目，下游卻看不到，只能靠 derive 反推 PDF 本來就有的數字。

觸發案例：MU 資產負債表同時揭露**聚合**債務 `LongTermDebtAndCapitalLeaseObligations` $14,017M **與細項** `LongTermDebt` $11,533M + `FinanceLeaseLiabilityNoncurrent`。舊 allowlist first-match 只抓其一，另一個丟掉 → 前端對不上 PDF。

用戶定原則（/goal）：「**只要 PDF 上面有的、從 XBRL API 拿到的資料都要拿下來；聚合科目跟細項我們兩個都要拿**」，且 parse 不得自己運算補洞（專案鐵律）。

T3（100% 精準、對外、不可逆）→ 套完整 SOP：dev workspace 開發、不直接動 SoT、property/對抗測試、多 AI 對抗 review、ADR、可逆。

## Decision

新增 `scripts/face_completeness.py`，在 `build_separated.py` 寫完 `facts.json` 後（step 4b）跑一次**純加性 face-completeness pass**：

1. **face 成員用 presentation linkbase 權威 `axis` 欄列舉**（`edges_pre`，由 `full_linkbase.py` 寫；notes/OCI/equity 已濾）。凡 face concept 有 companyfacts 值、但 allowlist 漏掉 → 補成 `{section}_long_tail` row（`is_/bs_/cf_long_tail` bucket）。**聚合與細項並存**（兩者都是 face 成員就都收）。
2. **period-aware**：`edges_pre` 只有 Q/FY 標籤，YTD（6M→Q2、9M→Q3）映射到所屬季的 face 成員（`_owning_edge_period`）。duration window 對齊核心 extractor（Q 60-105 / 6M 160-200 / 9M 240-290 / FY 340-380 天，disjoint）；BS instant；CF instant fallback（cash balance / restricted cash，gated）。
3. **不新增任何 cal edge**：這些 concept 已在 calculation linkbase，補 edge 會讓 `cal_sum_sanity` 雙重計 → footing 不受影響（`edges:0`）。
4. **去重三重保護**：(a) source_account 已被核心 captured 的跳過；(b) 核心 uni 為 blank-source（net_income / shares_basic_millions / shares_diluted_millions）者，用 `concept_to_core_uni` + `present_blank_source_uni_keys` 防語意重複；(c) restatement 取 latest-`filed`（同 period 多筆時）。
5. **單位**：USD 照 ticker scale（USD_millions/thousands）；EPS（USD/shares）→ `USD_per_share` 不縮放；股數（shares）→ `millions_shares`（÷1e6）。
6. **`full_linkbase.role_to_axis` combined-statement 修正**：Statements of Operations & Comprehensive Income 合併表正確歸 IS（strip comprehensive token 後殘留 operations/income/earnings → IS；純 OCI → 排除）。
7. **fail-closed**（T3）：例外或缺必要輸入 → `build_separated` exit 3，不靜默出殘缺 facts.json。`--skip-face-completeness` 才能顯式 bypass。
8. **idempotent**：`augment_facts_file` 重跑不重複累加（已存在 long_tail row 偵測）。

## Alternatives considered

- **A. 把所有漏掉的 tag 補進 allowlist 核心 key** — 否決：違反 LOCKED uni_account 紀律（ADR-002 已定），且聚合+細項並存會讓核心 key 語意衝突。
- **B. 下游 derive 反推 PDF 缺的科目** — 否決：違反「parse 永不運算 / PDF 有就直接拿」原則；derive 反推的值會跟 filer baseline 對不齊，污染 source-of-truth 紀律。
- **C. 重寫 extractor 改成 denylist（收全部、只排除已知 notes）** — 否決：風險過大（會掃進 notes/dimensional 維度值），且破壞既有 first-match cross-check 契約。加性 pass 風險最小、可逆、零 regression。
- **D. 用關鍵字重新推導 axis** — 否決（self-review + subagent + Codex 都抓到）：presentation linkbase 的 `axis` 是權威來源，重推會誤分類 combined statement。改為**信任 `axis` 欄**。

## Consequences

**正面**：
- PDF 三表面所有 companyfacts 可得科目全收（聚合+細項並存），下游不再靠 derive 反推。
- 純加性 + 0 cal edge → footing / cal_sum_sanity 不受影響；既有 facts byte-stable（只新增 row）。
- fail-closed + idempotent → 正常 build 不會靜默出殘缺輸出，重跑安全。

**負面 / 待觀察**：
- facts.json row 數顯著增加（MU +809 / LITE +1395 / INTC +148 / SNDK +139 / AAOI +141）→ 下游 reader 須能容忍 `{section}_long_tail` bucket（與 ADR-002 同類，已支援）。
- **下游 display 決策待辦（本 ADR 不含）**：前端如何呈現「聚合行 vs 細項行」（哪個當主行、哪個縮排）是獨立議題，留待 capture 穩定後處理（即原 MU BS display 問題）。
- Codex round-4 記一個 future-taxonomy 殘留風險（P3，非阻擋）：未來若出現 cash-prefix 開頭、duration 型、又不含 increasedecrease 子字串的新 concept 可能漏過 CF instant allowlist——目前 repo 無此案例，且該 concept 也會被核心 map 或 duration entry 攔到。

**驗證**：`test_face_completeness.py`（20+ case）+ 既有測試共 42 綠；5-ticker e2e `remaining_gap=0 / true_dup=0 / semantic_dup=0`；YTD 保留；CF cash-balance 收下；golden regression 0 missing / 0 changed；idempotent。GPT-5.5 xhigh Codex 4 輪 + 獨立 subagent 對抗審查。

**可逆**：`--skip-face-completeness` 一鍵 bypass；移除 step 4b 即回到 ADR-002 行為。

## Rollout（待人類授權，本 ADR 不含 production 寫入）

1. ~~併回 SoT + sync runtimes~~（2026-06-06 完成）
2. re-parse 5 ticker（MU/LITE/INTC/SNDK/AAOI）→ re-upsert production（**待用戶授權**）
3. 前端 display「聚合 vs 細項」決策（獨立 follow-up）
