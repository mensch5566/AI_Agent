# parse-twse-ixbrl — 台股 XBRL 財務數據解析

從本地 TWSE XBRL HTML 解析完整三張財報，寫入 Supabase 四張表。

## 使用方式

```
/parse-twse-ixbrl <ticker> [periods...]
```

- **ticker**（必須）：股票代號，如 `2454`
- **periods**（可選）：指定期別如 `Q4_FY2025`，預設解析所有本地找到的期別

## 數據管道流程

```
本地 TWSE iXBRL HTML（手動下載至 ~/Downloads 或 iCloud Obsidian Vault）
    ↓ batch_parse.py
解析 iXBRL → 提取三張報表全量指標（IS / BS / CF）
    ↓ 單季處理
    Q1：直接讀 Jan-Mar context
    Q2/Q3：IS 用單季 context，CF 用 YTD 減前期
    Q4：IS + CF = 全年 − Q3_YTD；BS 取 Dec 31
    ↓ 寫入
financial_facts   → XBRL 原始數值（source = XBRL_TWSE）
financial_metrics → 衍生計算指標（source = COMPUTED_FROM_XBRL_TWSE）
    ↓ 補充（另跑 /supplement-financials）
financial_supplement → NotebookLM 補值（source = NB_SUPPLEMENTED）
    Segments / 地區別營收 / Non-GAAP
```

## 寫入的指標

### financial_facts（XBRL 原始）— 每期 ~87 項

**損益表（IS）— 30 項**

| 代碼 | 指標 | 說明 |
|---|---|---|
| 4000 | operating_revenue | 營業收入 |
| 5000 | cost_of_revenue | 營業成本 |
| 5900 | gross_profit | 營業毛利 |
| 6100 | selling_expenses | 推銷費用 |
| 6200 | general_admin_expenses | 管理費用 |
| 6300 | r_and_d_expenses | 研究發展費用 |
| 6450 | expected_credit_loss | 預期信用減損利益（損失） |
| — | operating_expenses | 營業費用合計 |
| 6900 | operating_income | 營業利益 |
| 7100 | interest_income | 利息收入 |
| 7010 | other_income | 其他收入 |
| 7020 | other_gains_losses | 其他利益及損失 |
| 7050 | interest_expense | 財務成本 |
| 7060 | equity_method_income | 採用權益法認列損益 |
| — | non_operating_income_expense | 營業外收入及支出合計 |
| 7900 | income_before_taxes | 稅前淨利 |
| 7950 | income_tax_expense | 所得稅費用 |
| 8200 | net_income | 本期淨利（含少數股東） |
| 8610 | net_income_parent | 歸屬母公司業主淨利 |
| 8620 | net_income_nci | 歸屬非控制權益淨利 |
| 8300+ | oci_* | 其他綜合損益各項（4項） |
| — | other_comprehensive_income | 本期其他綜合損益（稅後） |
| 8500 | total_comprehensive_income | 本期綜合損益總額 |
| 8710 | comprehensive_income_parent | 綜合損益歸屬母公司業主 |
| 8720 | comprehensive_income_nci | 綜合損益歸屬非控制權益 |
| 9710 | basic_eps | 基本每股盈餘（元） |
| 9810 | diluted_eps | 稀釋每股盈餘（元） |

> **EPS 說明**：Q4 EPS 為 XBRL 全年值（如 FY2025 = 66.16元），無法從 XBRL 取得 Q4 單季 EPS。

**資產負債表（BS）— 47 項**（資產 21 + 負債 17 + 權益 9）

**現金流量表（CF）— 10 項**（營業 3 + 投資 2 + 融資 2 + 彙總 3）

> CF 說明：Q2/Q3 的 CF 由 YTD 減前期推算（XBRL 無單季 CF context）。

---

### financial_metrics（衍生計算）— 每期 14 項

**損益表衍生**

| 指標 | 公式 | 說明 |
|---|---|---|
| gross_margin_pct | gross_profit / operating_revenue × 100 | 毛利率 |
| operating_margin_pct | operating_income / operating_revenue × 100 | 營業利益率 |
| pretax_margin | income_before_taxes / operating_revenue × 100 | 稅前淨利率 |
| net_margin_pct | net_income / operating_revenue × 100 | 稅後淨利率 |
| r_and_d_ratio | r_and_d_expenses / operating_revenue × 100 | R&D 費用率 |
| opex_ratio | operating_expenses / operating_revenue × 100 | 營業費用率 |
| effective_tax_rate | income_tax_expense / income_before_taxes × 100 | 有效稅率 |
| interest_coverage | operating_income / interest_expense | 利息保障倍數 |

**資產負債表衍生**

| 指標 | 公式 | 說明 |
|---|---|---|
| current_ratio | total_current_assets / total_current_liabilities | 流動比率 |
| debt_to_equity | total_liabilities / total_equity | 負債權益比 |
| equity_ratio | total_equity / total_assets | 自有資本比率 |

**跨表衍生**

| 指標 | 公式 | 說明 |
|---|---|---|
| roe | net_income / total_equity × 100 | 股東權益報酬率 |
| roa | net_income / total_assets × 100 | 資產報酬率 |
| fcf | operating_cash_flow + capex | 自由現金流（capex 為負值） |

---

### financial_supplement（NotebookLM 補值）— 另跑

XBRL 未提供的細分維度資料，從 NotebookLM 對應筆記本補值：

| category | metric | 說明 | 來源 |
|---|---|---|---|
| geography | revenue_by_geography | 地區別營收（台灣/亞洲/其他） | 年報附注 |
| segment | segment_*_revenue | 業務分部營收（若公司有揭露） | Earnings Call |
| non_gaap | eps_non_gaap | Non-TIFRS EPS | Earnings Call |
| non_gaap | operating_margin_non_gaap | Non-TIFRS 營業利益率 | Earnings Call |

> 聯發科（2454）為「單一營運部門」，無業務分部揭露；地區別（台灣/亞洲/其他）已補入。

---

## 檔案搜尋路徑

1. `~/Downloads/tifrs-fr1-m1-ci-cr-{ticker}-*.html`
2. `~/Library/Mobile Documents/iCloud~md~obsidian/.../Semiconductors/{ticker}/MOPS Filings/XML/`

## 已知限制（Known Limitations）

| 項目 | 說明 |
|---|---|
| Q4 EPS | XBRL Q4 年報只有全年 EPS，Q4 單季 EPS 無法取得。`basic_eps`/`diluted_eps` 在 Q4 存的是全年值（FY2025 = 66.16/66.03） |
| Q2/Q3 CF | XBRL 無單季 CF context，由 YTD 減前期計算。若前期檔案不存在則存 YTD 並輸出警告 |
| Q4 IS | FY − Q3 YTD 計算。若 Q3 檔案不存在則存全年並輸出警告 |
| 業務分部 | XBRL 標籤無分部維度，需由 NotebookLM 補值（/supplement-financials） |
| 公司特有科目 | 若解析數量明顯少於 87，代表該公司有自訂標籤，需手動補進 XBRL_MAP |
| financial_metrics 格式 | pct 指標存小數（0.4814），前端 `fmtVal` 乘 100 顯示為 48.1%，勿與舊格式（48.14）混用 |

---

## 驗證方法（新標的跑完後必做）

```bash
uv run --with supabase python3 -c "
from supabase import create_client
env = {k.strip(): v.strip() for line in open('.env') for k, v in [line.split('=',1)] if '=' in line}
sb = create_client(env['NEXT_PUBLIC_SUPABASE_URL'], env['SUPABASE_SERVICE_ROLE_KEY'])
ticker = '2454'  # 換成要驗的 ticker
checks = [
    ('financial_facts',   'Q1_FY2025', 'operating_revenue', 153_312_237),
    ('financial_facts',   'Q3_FY2025', 'gross_profit',       66_111_891),
    ('financial_facts',   'Q4_FY2025', 'basic_eps',          66.16),
    ('financial_metrics', 'Q1_FY2025', 'gross_margin_pct',   0.4814),
]
for table, period, metric, expected in checks:
    r = sb.table(table).select('value').eq('ticker',ticker).eq('period',period).eq('metric',metric).execute()
    val = r.data[0]['value'] if r.data else None
    ok = val is not None and abs(val - expected) / max(abs(expected), 1) < 0.001
    print(f\"{'✅' if ok else '❌'}  {table:20s} {period:12s} {metric:25s}  got={val}\")
"
```

---

## CHANGELOG

### 2026-04-09（本次 session 重大修復）

**覆寫原 Haiku session 的問題，完整重建解析管道**

| Bug | 症狀 | 根因 | 修法 |
|---|---|---|---|
| Q3/Q4 不顯示 | 前端只見 Q1/Q2 | Supabase 預設 1000 row limit 截斷 20 期資料 | API 改用 range() pagination |
| Annual EPS 顯示四季加總 | FY2025 EPS = 117.9 | `SUM_EXCLUDE` 用舊名 `eps_basic`，XBRL 用 `basic_eps` | 兩種名稱都加進 SUM_EXCLUDE |
| EPS 顯示整數 | 66.03 → "66" | `isEps()` 只檢查 `eps_*` 前綴 | 補上 `basic_eps`/`diluted_eps` |
| Ratios/Segments tab 空白 | Financial Ratios、Segments 無資料 | API 只查 financial_facts | API 補查 financial_metrics 和 financial_supplement 並注入 |
| Annual Ratios 為 null | toAnnual() 毛利率算出 null | 使用舊名 `revenue`，XBRL 用 `operating_revenue` | toAnnual() 加台股 fallback |
| Q2/Q3 CF 空白 | CF 科目不顯示 | CF 只有 YTD context | 解析 YTD 減前期 |
| scale 乘錯 | 所有金額 ×1000 | 誤將 `scale="3"` 套用 | 移除 scale 計算（原始數字已是千元） |
| financial_metrics 顯示 4814% | 毛利率顯示異常 | DB 存 48.14，前端再 ×100 | 改存小數（0.4814） |

**新增功能**
- 全量抽取：IS 30 項 + BS 47 項 + CF 10 項（原為 8 項）
- 單季正確處理：Q1 直讀、Q2/Q3 單季 context、Q4 FY−Q3_YTD
- IS 衍生指標新增：`effective_tax_rate`、`opex_ratio`、`interest_coverage`、`fcf`
- financial_supplement 地區別（台灣/亞洲/其他）寫入

---

## 執行方式

```bash
cd /Users/mensch5566/AI_Agent
uv run --with supabase --with lxml python3 \
  Tools/research-tools/parse-twse-ixbrl/batch_parse.py <ticker> [periods...]
```

## 範例

```bash
# 解析所有本地期別
uv run --with supabase --with lxml python3 \
  Tools/research-tools/parse-twse-ixbrl/batch_parse.py 2454

# 只解析指定期別
uv run --with supabase --with lxml python3 \
  Tools/research-tools/parse-twse-ixbrl/batch_parse.py 2454 Q4_FY2025
```
