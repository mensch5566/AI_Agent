# Financials Compose Schema

最後更新：2026-05-10

這份文件定義 `compose` skill 的資料契約：吃什麼、吐什麼、cell 層級的 status 規則、跟下游（`derive-analytics`、Supabase upsert、前端）之間的邊界。

## 設計原則（不能違背）

1. **Source-of-truth 優先**：揭露的數字 > 算出來的數字。compose 不發明值。
2. **Non-GAAP 是稀疏揭露片段，不是完整報表**：SEC Reg G 只強制 reconciliation，不強制揭露範圍與期數。所以 Non-GAAP 在「跨期」與「跨科目」兩個維度都可能有洞。
3. **Cell 層級的紀律**：每一格 (period, version, uni_account) 都必須有明確的 `status`，可以追溯到 source filing 或 derivation formula。沒辦法追溯的格子一律 `NOT_DISCLOSED`。
4. **Compose 不做運算**：compose 只組裝 + 標記。所有「運算」（恆等式補洞、ratio 派生）都在 `derive-base`（compose 之前）或 `derive-analytics`（compose 之後）做。

> 待頭腦風暴的議題：是否要把 Non-GAAP 強制呈現為「平行於 GAAP 的完整表」，還是承認它本來就只是稀疏 fragments。schema 設計成 cell-level，**兩種呈現方式都能 derive 出來**，所以這個議題暫時不會卡到實作。

---

## Pipeline 位置

```
parse-10QK-gaap        ──┐
                         ├─→ derive-base ──┐
parse-8k-nongaap       ──┘                 ├─→ compose ──→ derive-analytics
                                          │
parse-sec-cross-check  ──→ (audit corrections written back to GAAP json before derive-base)
```

- **Input**：`{TICKER}_gaap_derived.json`（10-Q/10-K + Q4 單季 + 單表內恆等式補洞）
              `{TICKER}_nongaap_derived.json`（8-K + 單表內恆等式補洞，例如 COGS = Rev - GP）
- **Output**：`{TICKER}_composed.json`
- **Downstream consumer**：`derive-analytics`、Supabase upsert script、Financials Viewer 前端

---

## Composed JSON Schema（v1）

```jsonc
{
  "metadata": {
    "ticker": "INTC",
    "company": "Intel Corporation",
    "currency": "USD",
    "unit": "millions",
    "compose_run": "2026-05-10-1430",
    "compose_version": "1.0",
    "input_sources": {
      "gaap_derived":    "Khouse/.../parse-10QK-gaap/INTC_gaap_derived.json",
      "nongaap_derived": "Khouse/.../parse-8k-nongaap/INTC_nongaap_derived.json"
    },
    "exclusion_list_version": "INTC_v1_2026-05-10",
    "warnings": [
      // 例如：「Non-GAAP definitional change suspected between Q2_FY2025 and Q3_FY2025」
    ]
  },

  "cells": [
    {
      "period":       "Q1_FY2025",      // Q1_FY2025, Q4_FY2025, FY2025 ...
      "version":      "GAAP",            // GAAP | NON_GAAP
      "statement":    "income_statement",// income_statement | balance_sheet | cash_flow_statement
      "uni_account":  "revenue",
      "value":        12667.0,           // null if status=NOT_DISCLOSED
      "unit":         "USD_millions",    // USD_millions | USD_per_share | percent | shares_millions
      "status":       "SOURCE_OF_TRUTH", // 見下方四種狀態
      "provenance": {
        "source_filing":  "10-Q",        // 10-Q | 10-K | 8-K | DERIVED | EXCLUSION_RULE
        "source_account": "Net revenue", // PDF 上的字面 label（揭露原文）
        "xbrl_tag":       "us-gaap:Revenues",  // 僅 GAAP from XBRL
        "audit_source":   null,          // null 或 "MANUAL_AUDIT_FROM_PDF"
        "formula":        null,          // 僅 DERIVED_FROM_DISCLOSED 才填
        "exclusion_rule": null           // 僅 EXCLUDED_FROM_NONGAAP 才填
      },
      "comparability": {
        "definitional_baseline": "INTC_nongaap_def_2025",  // 同一定義 ID 內的 cell 才可比
        "flags": []                      // ["DEFINITION_CHANGED", "RESTATED", ...]
      }
    }
    // ... 一個 (period, version, uni_account) 一筆
  ]
}
```

### 為什麼 cells 是 flat array 不是巢狀字典

巢狀（`by_period[period][version][uni_account]`）讀起來直觀，但：
- 缺項就要決定「key 不存在」vs「key 存在 value=null」的語意 → 容易踩坑
- 篩選跨維度（例如「所有 NOT_DISCLOSED」「所有 Non-GAAP Q1_FY2025」）要寫巢狀走訪
- 上 Supabase 一定要拍平成 row

flat array + cell-level status 是 schema 對 Supabase / 前端 / 篩選都最友善的形式。

---

## Cell Status 四種狀態

| status | 意思 | `value` | `provenance` 必填 |
|---|---|---|---|
| `SOURCE_OF_TRUTH` | 直接從 8-K/10-K/10-Q PDF 或 XBRL 揭露 | 數值 | `source_filing` + `source_account` |
| `DERIVED_FROM_DISCLOSED` | 同一 source 內的算術恆等式（COGS = Rev - GP；Q4 = FY - 9M） | 數值 | `source_filing="DERIVED"` + `formula` |
| `EXCLUDED_FROM_NONGAAP` | 結構性 = 0（restructuring、SBC、acquired-IP amortization 等，依 exclusion list） | `0.0` | `source_filing="EXCLUSION_RULE"` + `exclusion_rule` |
| `NOT_DISCLOSED` | 沒揭露、無法導出 | `null` | `source_filing="NOT_DISCLOSED"` |

> 重要：`EXCLUDED_FROM_NONGAAP` ≠ `NOT_DISCLOSED`。前者是「公司明確把這項從 Non-GAAP 拿掉」，後者是「公司沒提這項」。語意完全不同，下游處理也不同（前者可進加總，後者要當缺資料）。

---

## Exclusion List（per-ticker config）

每家公司的 Non-GAAP 定義不同，需要一份配置告訴 compose「哪些 GAAP 列在 Non-GAAP 一律算 0」。

位置：`~/.cc-switch/skills/compose/ticker_configs/{TICKER}.json`

```jsonc
{
  "ticker": "INTC",
  "definitional_baseline_id": "INTC_nongaap_def_2025",
  "valid_from": "FY2025",
  "valid_until": null,                // null = 還在用
  "exclusion_list": [
    {
      "uni_account": "restructuring_charges",
      "rule": "STRUCTURAL_EXCLUSION",
      "rationale": "Intel 8-K Q1 FY25 reconciliation: 'Adjustments: + Restructuring and other charges'",
      "from_period": "Q1_FY2025"
    },
    {
      "uni_account": "amortization_of_acquired_intangibles",
      "rule": "STRUCTURAL_EXCLUSION",
      "rationale": "8-K reconciliation: '+ Amortization of acquired intangibles'",
      "from_period": "Q1_FY2025"
    }
  ],
  "definition_change_log": [
    // 例如：「FY2026 Q3 起 Non-GAAP 不再排除 SBC，新建 INTC_nongaap_def_2026 baseline」
  ]
}
```

> **配置維護成本**：使用者得對每家公司讀過一次 8-K reconciliation table，把「+ X」的項目登記進 exclusion list。這是 compose 紀律的代價，沒辦法自動化。
> 
> **不維護的後果**：所有 Non-GAAP 沒揭露的格子全部變 `NOT_DISCLOSED`，下游無法區分「公司結構性排除」vs「真的沒講」。

---

## 跨期可比性（Comparability）

每個 cell 都帶 `comparability.definitional_baseline`。**只有 baseline ID 相同的 cells 才能拿來做趨勢分析**。

定義改變的觸發：
- 8-K reconciliation table 的「Adjustments」項目集合變了（多加 / 減少一項）
- 公司在 8-K 註明 "redefined Non-GAAP measures"
- 重大事件導致歷史值被 restate

→ `parse-8k-nongaap` 之後可以加一個 reconciliation-set 比較器，自動偵測改變並丟 warning。**這是 future work，目前手動維護**。

---

## 顆粒度不對齊處理

8-K 的 Non-GAAP 有些列**結構上跟 GAAP 不一樣**：

| 情況 | compose 處理 |
|---|---|
| 8-K 給合併列（如 `R&D + MG&A combined = 4271`），不拆 | 在 Non-GAAP 表加一筆 `uni_account: rnd_and_mgna_combined`；GAAP 表不存在這筆 |
| 8-K 給比率（如 `gross_margin_pct = 39.2`），GAAP 表沒這列 | Non-GAAP 表加 `uni_account: gross_margin_pct`，`unit: percent`；GAAP 表沒這筆 |
| GAAP 有 `restructuring_charges`，Non-GAAP 對應依 exclusion list = 0 | GAAP 表正常，Non-GAAP 表標 `EXCLUDED_FROM_NONGAAP, value: 0` |
| GAAP 有 `cost_of_sales`，Non-GAAP 沒揭露但能由 `revenue - gross_profit` 導出 | derive-base 做掉這個推導，compose 收到的就是 `DERIVED_FROM_DISCLOSED` |
| GAAP 有 `selling_general_administrative`，Non-GAAP 也沒拆出來 | Non-GAAP 表標 `NOT_DISCLOSED, value: null` |

→ 結論：**GAAP cells 跟 Non-GAAP cells 的 uni_account 集合不必相同**。schema 已經支援這個（cells 是 flat array，每筆獨立）。

---

## 比率與金額同時揭露時的優先順序

8-K 經常同時給 `gross_profit = 4961` 跟 `gross_margin_pct = 39.2`，這兩個值算起來會有 rounding mismatch（`4961 / 12667 = 39.16%`）。

規則：
- **揭露的比率值** → `SOURCE_OF_TRUTH` 寫入 `gross_margin_pct` cell
- **揭露的金額** → `SOURCE_OF_TRUTH` 寫入 `gross_profit` cell
- 兩者並存，**不互相覆寫**
- `derive-analytics` 之後算 ratio 時，看到 cell 已存在 `SOURCE_OF_TRUTH` 比率，不再 recompute

---

## Cross-Source 紀律（不可違背）

| 動作 | 允許？ |
|---|---|
| GAAP 表的 cell 從 8-K Non-GAAP 拿值補 | ❌ 絕對禁止 — 8-K Non-GAAP ≠ GAAP，混了就是污染 |
| Non-GAAP 表的 cell 從 GAAP 拿值補（「兩邊剛好一樣，所以借用」） | ❌ 禁止 — 你不知道是真的一樣還是 NLM 沒抽到 |
| Non-GAAP 表的 cell 由「同一個 8-K 內」的揭露值算術導出 | ✅ 允許（DERIVED_FROM_DISCLOSED） |
| GAAP 表的 cell 由「同一份 10-K/10-Q 或同 source XBRL」算術導出 | ✅ 允許（DERIVED_FROM_DISCLOSED） |
| GAAP Q4 單季 = GAAP FY annual − GAAP 9M | ✅ 允許（同 source = GAAP，同公司同年度） |
| GAAP Q4 = GAAP FY annual − sum(quarterly Q1+Q2+Q3) | ✅ 允許 |

→ **derive-base 跟 compose 都不可跨 GAAP/Non-GAAP 邊界補值**。cross-source 補值會直接讓「Non-GAAP 跨期不可比」變得無從追溯。

---

## Compose 的 Reconciliation 自驗證（建議實作）

對每個 (ticker, period)，compose 應該自驗證 8-K 的 reconciliation 數學是否成立：

```
GAAP value + Σ(adjustments) ≟ Non-GAAP value
```

例（INTC Q1 FY25 operating income）：
```
GAAP OI = -301
+ restructuring             156
+ SBC                       XXX
+ amortization              XXX
+ ...
= Non-GAAP OI = 690
```

若 reconciliation 對不上：
- 不寫入該 cell
- log warning 到 `compose_warnings.md`
- 留待人工審查

> **這需要 parse-8k-nongaap 也抽 adjustments 的明細**，目前只抽 final Non-GAAP 值。要做 reconciliation 自驗證，需要先擴展 parse-8k-nongaap 的 schema。**先列入 future work**。

---

## 與下游介面

### Supabase upsert
- 從 `cells` array 直接拍平 → `financial_facts_v2` 表
- `status` 直接當 column
- `provenance` 拍平成 `source_filing / source_account / xbrl_tag / formula / exclusion_rule`

### Financials Viewer 前端
- 讀 cells，依 `(period, version, uni_account)` 做 pivot 渲染
- `NOT_DISCLOSED` cell 顯示 `—`
- `EXCLUDED_FROM_NONGAAP` cell 顯示 `0` + tooltip「公司 Non-GAAP 定義已排除」
- `DERIVED_FROM_DISCLOSED` cell 顯示數值 + tooltip 顯示 formula

### derive-analytics
- 只讀 `SOURCE_OF_TRUTH` 跟 `DERIVED_FROM_DISCLOSED` 的 cells 做運算
- `EXCLUDED_FROM_NONGAAP`：在加總時當 0 處理（合理，因為公司就是這樣定義）
- `NOT_DISCLOSED`：跳過該 ratio 計算，輸出該期該 ratio 為 null

---

## 已知限制（Known Limitations）

1. **Reconciliation 自驗證未實作**：依賴 parse-8k-nongaap 先擴 schema 抽 adjustments。
2. **Definition change 未自動偵測**：靠人工讀 8-K 維護 `definitional_baseline_id`。
3. **Exclusion list 維護成本**：每家公司第一次都要人工建。
4. **跨年度可比性**：跨 fiscal year 的 Non-GAAP 定義變動，目前只能用 `definitional_baseline_id` 切版本，沒有自動 bridging（例如新舊定義的 mapping）。
5. **重編 / 更正（restatement）**：公司事後 restate Non-GAAP 歷史值的處理流程未定義。

---

## CHANGELOG

### 2026-05-10（初版）
- 從 INTC + SNDK 早期實驗萃取出來
- 確立 cell-level + 4-status 模型
- 確立 derive-base / compose / derive-analytics 三段論
- 確立 cross-source 不補值紀律
