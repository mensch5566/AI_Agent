# parse-twse-ixbrl — 台股 XBRL 財務數據解析

從本地 TWSE XBRL HTML 解析財務數據，寫入 Supabase。完整管道的第一步。

## 使用方式

```
/parse-twse-ixbrl <ticker> [--skip-verify] [--notebook <name>] [periods...]
```

## 參數

- **ticker**（必須）：股票代號，如 `2454`（聯發科）
- **--notebook**（建議）：NotebookLM 筆記本名稱，用於驗證 XBRL 數據正確性
- **--skip-verify**（可選）：跳過 NotebookLM 驗證，直接寫入
- **periods**（可選）：指定期別如 `Q4_FY2025`，預設解析所有本地找到的檔案

## 數據管道流程

```
TWSE HTML 檔案（手動下載）
    ↓ batch_parse.py
解析 iXBRL HTML → 提取 8 項 GAAP 原始指標
    ↓ NotebookLM 驗證（需提供筆記本名稱）
比對 XBRL 數值 vs NotebookLM，差異 > 1% 列出人工複審
    ↓ 確認後寫入
financial_facts   → source = 'XBRL_TWSE'（8 項 GAAP 原始指標）
financial_metrics → source = 'COMPUTED_FROM_XBRL_TWSE'（7 項派生比率）
    ↓ 接著執行
/supplement-financials → 補足 Segments、Non-GAAP（寫入 financial_supplement）
```

## 寫入的指標

**financial_facts（XBRL 原始）**

| 指標 | 說明 |
|---|---|
| operating_revenue | 營業收入 |
| income_before_taxes | 稅前淨利 |
| net_income | 本期淨利 |
| total_current_assets | 流動資產 |
| total_assets | 資產總計 |
| total_current_liabilities | 流動負債 |
| total_liabilities | 負債總計 |
| total_equity | 權益總額 |

**financial_metrics（派生計算）**

| 指標 | 公式 |
|---|---|
| current_ratio | 流動資產 / 流動負債 |
| debt_to_equity | 負債 / 權益 |
| equity_ratio | 權益 / 資產 |
| net_margin_pct | 淨利 / 營收 × 100 |
| roe | 淨利 / 權益 × 100 |
| roa | 淨利 / 資產 × 100 |
| pretax_margin | 稅前淨利 / 營收 × 100 |

## 範例

```
/parse-twse-ixbrl 2454 --notebook 聯發科研究筆記
/parse-twse-ixbrl 2454 --notebook 聯發科研究筆記 Q4_FY2025
/parse-twse-ixbrl 2454 --skip-verify
```

## 執行腳本

```bash
python3 batch_parse.py <ticker> [--skip-verify] [--notebook <name>] [periods...]
```

檔案來源搜尋順序：
1. `~/Downloads/tifrs-fr1-m1-ci-cr-{ticker}-*.html`
2. `~/Library/Mobile Documents/iCloud~md~obsidian/.../Semiconductors/` 遞迴搜尋

## NotebookLM 驗證說明

執行時若未提供 `--notebook`，會互動式詢問筆記本名稱。
筆記本名稱每次都需提供，因為筆記內容常變動，不應硬編碼。
