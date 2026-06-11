---
type: adr
id: ADR-004
status: deferred
tier: T3
created: 2026-06-09
supersedes: none
related: docs/superpowers/specs/2026-06-09-sndk-label-text-fallback-design.md
---

# ADR-004：XBRL 值來源 companyfacts API → raw instance document（extension concepts）

> 狀態：**deferred**（已立案，未排程）。獨立 T3 專案，非 SNDK PDF-faithful blocker 的修法。
> Codex（GPT-5.5）收斂結論：對「現有 5 ticker 上線」不必要、屬過度工程；但這是「未來新 extension 科目連『值』都自動兼容」的**根本解**。

## Context

`parse-10QK-gaap/scripts/xbrl_extract.py`（line ~169）的值來源是
`https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json`。

SEC 設計上 companyfacts API **只暴露標準分類**（us-gaap / dei / srt），**不含公司 extension 概念**（`sndk:`、`mu:`…）。後果：任何以 extension concept 標記的 face 行，pipeline **拿不到值**，即使該 concept 在 presentation linkbase 的 face 上有 arc + 官方 label。

已知受害案例：
- `sndk:BusinessSeparationCosts`（SNDK IS face）— companyfacts 完全沒有；值目前只存在於 legacy `AGENT_CLASSIFIED`（人工從 PDF 讀入）的 fact。
- `mu:` government-incentives extension tag（MU）— 同類缺值，先前已 deferred。

> 對照：`us-gaap:GainLossOnSaleOfBusiness`（標準）在 companyfacts **有**值（含 90 天單季 context），所以標準科目不受此限。

## Decision（提議，未核可）

把 GAAP 三表值來源從 companyfacts API **遷移到該 filing 的 raw XBRL instance document（`_htm.xml`）**，instance doc 內含 extension concept 與其值。遷移後：

1. capture-everything（`face_completeness.py`）可把每個 face 行**連 concept 帶值**一起 capture（含 `sndk:`/`mu:` extension）。
2. resolver 走既有 tag/concept 路徑即可定位 ordinal，**無需** label-text fallback（ADR-004 上線後，2026-06-09 的 label fallback 變成純防禦備援）。
3. 未來新一期出現的新 extension 科目**值層面自動兼容**——完成 /goal 第二部分「值」的那一半。

## Alternatives considered

- **A. 維持 companyfacts API + per-row 人工/NLM 補 extension 值** — 現狀。缺點：每個 extension 科目都要人工，不可規模化，且 legacy `AGENT_CLASSIFIED` 機制脆弱。
- **B. 只做 label-text fallback（2026-06-09 已實作）** — 解了「ordinal/顯示」與「標準科目 future-proof」，但**沒解 extension 值缺口**。對現有 5 ticker 足夠，對未來新 extension 科目不足。
- **C.（本 ADR）instance-doc 值來源** — 根本解，但最大改動。

## Consequences

- T3 完整 SOP：design gate → Codex 對抗收斂 → property test（instance vs companyfacts 對標準科目須 1:1 一致，零 regression）→ 全 5 ticker 重抽重驗 → 可逆。
- 風險：instance doc 解析比 companyfacts JSON 複雜（context/unit/period 維度、dimensional facts 過濾、scale）；須確保標準科目值與現行 companyfacts 完全吻合才可切換。
- unit/scale auto-detect、duration 視窗（單季 60-100d / 年報 350-380d）等既有邏輯須沿用。

## 開工前置

- 重讀 `parse-SEC-supplement` skill（已有 `parse_instance_xbrl.py` 解 instance doc 的 dimensional 經驗可借鑑）。
- 確認 instance doc 取得管道（EDGAR filing index → `_htm.xml`）與快取策略。
