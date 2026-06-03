---
type: adr
id: ADR-002
status: proposed
tier: T3
created: 2026-06-03
supersedes: none
related: docs/superpowers/specs/2026-06-02-parse-bs-long-tail-design.md
---

# ADR-002：Balance Sheet long-tail catch-all（補實作 + suppression 語意修正）

> 格式：Context / Decision / Alternatives / Consequences（對齊 ADR-001）。
> 狀態：**proposed**（Design gate 中，待 Codex round-2 收斂 + 人類核可才轉 accepted）。
> 完整設計見 spec：`docs/superpowers/specs/2026-06-02-parse-bs-long-tail-design.md`。

## Context

跨 ticker BS footing 稽核（`tmp/parse-bs-footing-audit-worklist.md`）發現未映射的標準 us-gaap BS tag 被 `parse-10QK-gaap` **直接丟掉**（LITE 18 期、MU 16 期、INTC/SNDK 數期），導致 BS 表面對不平、個別科目行漏抓。

根因：架構文件（`docs/financials-architecture.md`）規定「不在 90 個 LOCKED 核心 uni_account 的科目要進該 section 的 long-tail bucket」，但 **extractor 從沒實作 BS 的 5 個 bucket**（只實作了 IS/CF 的 composite-fallback）。`financials-core-checklist.md`（LOCKED v5）+ 紀律「禁止自由創造新 uni_account、升級 core 要走 checklist 流程」限制了修法空間：不能把公司特殊科目硬塞核心 key。

T3（100% 精準、對外、不可逆）→ 套完整 SOP：先審再上、property/對抗測試、多 AI 對抗、ADR、可逆。

## Decision

補實作 BS long-tail catch-all，**零新核心 uni_account**：

1. **② 類（無核心歸屬）→ BS long-tail bucket**：在 `build_separated.py`（有 cal linkbase + raw companyfacts）偵測 face-BS role 內、BS 小計底下、未被核心 captured 的 us-gaap leaf 子科目，emit 成對應 bucket（`current_asset_long_tail` 等 5 個），帶 `weight`（cal）+ `rolls_up_to`（父小計）。section 分類用 **cal 父小計 deterministic 決定，不用 LLM**。
2. **① 類（核心科目的同義/別名 tag）→ 補 candidate 到既有核心 key**（`xbrl_extract.py`/inline，first-match-wins，保 cross-check）。非新 uni_account，= MU 應收 / LITE ASC606 先例。
3. **③ 類（跨多核心 key 的合併 tag）→ 逐筆裁決**（傾向當 bucket 合併行）。
4. **前端 suppression 語意修正**：suppression 只在 target row `kind === "core"` 時觸發，subtotal target（結構性 rolls_up_to）不抑制——否則 BS bucket 因 rolls_up_to=subtotal（永遠 populated）被全濾成空。
5. **Phase 0 前置（硬擋）**：`full_linkbase.py` cal period label 改 **fiscal-year-aware**（現為月曆推導，非 12 月結 ticker fiscal 位移）；leaf 偵測 **role-scoped** 到 face-BS role。
6. **防禦式設計**：拿不到值 / cal 異常 → 寫一級 anomaly report，**不 silent-drop**。

## Alternatives considered

- **A. 逐 tag 補核心 key（全部）** — 否決：對 ② 類特殊項目會新增/濫用核心 key，違反 LOCKED uni_account 紀律（用戶 round 中明確反對）。
- **B. 純前端 hints-only suppression**（Codex round-1 建議）— 部分採納但改良：需把現有靠 `metadata.rolls_up_to` 抑制的 INTC/LITE D&A composite 全遷進 `LONG_TAIL_ROLLUP_HINTS`，否則 regress 成雙顯。改用 **kind-aware guard**（零遷移、零 regression）。
- **C. 偵測放 `xbrl_extract.py`** — 否決：該層只有 companyfacts、無 cal 父子結構，section 分類得靠 tag 名 heuristic/LLM，較不穩。`build_separated` 有 cal + raw（Codex round-1 確認可採）。
- **D. diff=0 等價驗證當 gate** — 否決（NLM round）：對「修漏抓」這種改動 diff=0 只會完美複製漏抓 bug（Golden Master 盲點）。gate 改「diff = 恰好預期新增、零既有核心值改動」。
- **E. TLE/bitmask O(1) 階層儲存**（NLM 提）— 否決：rolls_up_to 僅 1-2 層淺階層，YAGNI。

## Consequences

- **正向**：BS footing 對平、不丟值、不新增核心 key、前端幾乎不用改（5 bucket 早已接好）；anomaly report 把漏抓/拿不到/cal 異常變可審。
- **成本/風險**：Phase 0 period-mapping 修動到 linkbase 抽取（影響所有 ticker，需 12 月結 byte-identical 回歸驗證）；前端 suppression 改動需保既有 D&A/SG&A 抑制不變；已上線 INTC/SNDK/LITE 需 re-parse + re-upsert（預期 diff≠0、僅 additive）。
- **不解**：B 類 extension tag（`mu:`/`intc:` 等）companyfacts 拿不到值 → 維持 Known Limitation，要補值需另建 instance-XML 抽取能力（獨立案）。
- **可逆**：純 git revert + re-upsert known-good；無 schema migration。

## Validation gate（T3）

Phase 0 過（MU/LITE/SNDK cal↔facts period 100% 對齊、12 月結 byte-identical）→ Phase 1 MU：A 類/companyfacts-addressable residual=0、B 類列報、零新核心 uni_account、零 double-count、cal sanity 0❌ → Codex 多 AI 對抗收斂 + 人類核可 → re-parse/re-upsert 已上線 ticker（diff=預期新增）。
