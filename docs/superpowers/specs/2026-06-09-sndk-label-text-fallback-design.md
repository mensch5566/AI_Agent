# Design: 窄 fail-closed「PDF label → face concept」ordinal fallback (SNDK)

Date: 2026-06-09 / Tier: T2 (adapter/resolver layer, parser 不動) / Status: design-converged (Codex GPT-5.5 round1)

## 問題

SNDK IS 有 3 個 face 行卡住 coverage gate（PDF-faithful 上線阻塞）：

| source_account (PDF 文字) | uni_account | 真正 concept (在 face presentation) |
|---|---|---|
| Gain on business divestiture | nonoperating_long_tail | us-gaap:GainLossOnSaleOfBusiness |
| Loss on business divestiture | nonoperating_long_tail | us-gaap:GainLossOnSaleOfBusiness |
| Business separation costs | operating_expense_long_tail | sndk:BusinessSeparationCosts |

這些是 **legacy `AGENT_CLASSIFIED` facts**（2026-06-03，早於 capture-everything），`classification_source=AGENT_CLASSIFIED` + `preservation_event=REEXTRACT_PRESERVED_PRIOR_CLASSIFICATION`，只帶 PDF 文字當 `source_account`、`xbrl_tag=None`。

現有 resolve 鏈（`sec_json_adapter.attach_display_metadata` preserved_pdf_label 分支）三步全 miss：
1. `resolve_label_ordinal_any(_local_name(source_account))` — source_account 是 PDF 文字，local-name 比不到 concept → ordinal=None
2. `resolve_via_uni_any(uni_account)` — long-tail bucket 無 canonical mapping → `NeedsNlmOrder`
3. `_try_audited_nlm_ordinal` — 無 NLM ordinal → ordinal=None → **gate 擋**

## 根因 + 為何不動 parser（Codex 收斂）

value source = `data.sec.gov/api/xbrl/companyfacts` API，**SEC 設計上不暴露 company extension 概念**（`sndk:`/`mu:`…）。但這 3 行的**值已存在**（靠 legacy fact）；缺的只是 **concept/ordinal 連結**。

presentation linkbase **已含**這兩個 concept 在 IS face，每個 displayable period 都有 order + 官方 label：
- `us-gaap:GainLossOnSaleOfBusiness`: terseLabel "Gain on business divestiture" / negatedTerseLabel "(Gain) loss on business divestiture"
- `sndk:BusinessSeparationCosts`: terseLabel "Business separation costs"

PDF 文字 source_account **本就是 XBRL terseLabel**，只是 concept link 沒記下來。

Codex 裁決：把 value source 從 companyfacts→raw instance（recover extension 值）是**更大、獨立**的根本工程（立為工單 B，見 `docs/adr/`），對「5 ticker 上線」是**過度工程**。當前正解 = adapter 層**窄 fail-closed label→face concept 解析**。

## 方案

新增 resolver 函式 `resolve_via_label_text(source_text, edges, labels, statement) -> (concept_local, ordinal, negated)`，接進 preserved_pdf_label 分支、`resolve_via_uni_any` borrow 失敗之後，作 NLM 前的最後一手。命中後：ordinal=該 concept 的 global 位置、display_negated=face edge 的 preferred_label 符號、resolved_concept=真 concept。`display_label` **維持 source_account PDF 原文不變**。

### 六條紀律（fail-closed，T3 精準）

1. **只 accepted face network**：候選僅來自 `matching_face_networks(edges, statement)`（排除 parenthetical/details/note/reconciliation）。無 face network → 直接 unresolved。
2. **只官方 label role**：比對 `labels[full_qname]` 的官方 role 文字（terse/negatedTerse/total/label/verbose…），**絕不**比對其他 row 的 source_account。
3. **normalize + 窄去括號**：lowercase、strip、去標點、collapse 空白；外加一個**很窄**的前綴去括號 `^\(...\)\s*`（`(gain) loss on business divestiture` → `loss on business divestiture`）。不做 token 啟發/同義詞。
4. **唯一 concept 命中**：normalized key 必須對應**恰好一個** distinct child_qname concept；0 個或 ≥2 個 → return (None,None,None) → unresolved（gate 擋）。
5. **不改 `source_account`**：它是 audit-preservation identity key，且是 period-exact PDF 顯示文字。只取 ordinal/negated/concept，display_label 仍 = source_account。
6. **全 5 ticker regression**：任何 label-based 修改後跑全 pytest+vitest+tsc + dry-run coverage，確認 MU/LITE/INTC/AAOI 不 regression。

### 符號（display_negated）

無論 PDF 寫 "Gain" 還是 "Loss" 變體，都唯一鎖定同一 concept GainLossOnSaleOfBusiness；display_negated 一律取 **face edge 的 preferred_label** 決定（既有 `_edge_negated` 機制，與 MU 已驗證一致）—— PDF-faithful 顯示用 face 的符號角色，非 source_account 字面。

## Future-proof 範圍（對 /goal 第二部分誠實）

- ✅ **未來新的標準 us-gaap face 科目** + **前端**：只要新科目在 face presentation 有 arc + 官方 label，這條 fallback 自動歸位（外加既有 tag_like / via_uni 路徑）。
- ❌ **未來新的 extension 科目（`sndk:`/`mu:`，companyfacts 不給值）**：值仍缺 → 屬工單 B（instance-doc value source）範圍，本方案不解。

## 不做（Codex 明確反對）

- ❌ 純前端修（gate 在 upsert 階段，render 前）
- ❌ 會在多 concept 間靜默選擇的 fuzzy matcher
- ❌ 改寫 source_account 成 tag
- ❌ 把 companyfacts→instance 遷移當成此 blocker 的第一手
