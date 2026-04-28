# parse-twse-ixbrl — 台股 XBRL 財務數據解析

從本地 TWSE XBRL HTML 解析完整三張財報，寫入 Supabase 四張表。

## 使用方式

```
/parse-twse-ixbrl <ticker> [periods...]
```

- **ticker**（必須）：股票代號，如 `2454`
- **periods**（可選）：指定期別如 `Q4_FY2025`，預設解析所有本地找到的期別

## 完整兩步流程

> 新標的或更新財報，**必須依序跑兩個 skill**：

### Step 1：/parse-twse-ixbrl（本 skill）

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
```

### Step 2：/supplement-financials（另一個 skill）

> **前置條件**：對應 ticker 的財報 PDF 已上傳至 NotebookLM

```
NotebookLM（對應 ticker 筆記本）
    ↓ 查詢 PDF 財報附注、法說會
    ↓ 寫入
financial_supplement → NB 補值（source = NB_SUPPLEMENTED）
```

**Step 2 補充的指標（XBRL 不提供）：**

| category | metric | 說明 |
|---|---|---|
| shares | weighted_avg_shares_basic | 加權平均流通股數－基本（從 EPS 附注取得） |
| shares | weighted_avg_shares_diluted | 加權平均流通股數－稀釋 |
| geography | revenue_by_geography | 地區別營收（年報附注） |
| segment | segment_*_revenue | 業務分部營收（如有，Earnings Call） |
| non_gaap | eps_non_gaap | Non-TIFRS EPS |
| non_gaap | operating_margin_non_gaap | Non-TIFRS 營業利益率 |

**Q4 的 weighted_avg_shares**：年報常只提供全年加權平均。原始年值可作為 annual disclosure 保存，但不得直接當作 Q4 單季值顯示在 quarterly view；若需要 Q4 單季 shares，應以 derived metric 另存於 `financial_metrics`。

**Annual 規則（台股 period-based statements）**：
- Annual 必須優先使用 `Q4` 財報直接揭露的 `FYxxxx` 值。
- 若沒有 direct `FYxxxx` 值，annual 應留空，不得以季度加總回填。
- 這條規則適用於 `income_statement`、`cash_flow_*`，以及有 direct annual disclosure 的 Taiwan supplement period series。

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

> **EPS 說明**：Q4 EPS 在 XBRL 常為全年值；parser 會優先以 `FY - 9M cumulative EPS` 還原 `Q4` 單季 EPS，只有在 `9M cumulative EPS` 不可得時，才 fallback 到 `FY - (Q1 + Q2 + Q3)`。annual mode 則應使用 direct `FY` EPS。

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
| Q4 EPS | XBRL Q4 年報通常只揭露全年 EPS。parser 應優先以 `FY - 9M cumulative EPS` 還原 `Q4` 單季 EPS；若 cumulative EPS 不可得且 `Q1~Q3` 單季 EPS 齊全，才 fallback 到 `FY - (Q1 + Q2 + Q3)`；若仍無法還原，quarterly 不得顯示全年值 |
| Annual period tables | 台股 annual 必須使用 direct `FYxxxx` disclosure；若缺 direct `FY`，不得以季度加總 fallback |
| Q2/Q3 CF | XBRL 無單季 CF context，由 YTD 減前期計算。若前期檔案不存在則存 YTD 並輸出警告 |
| Q4 IS | FY − Q3 YTD 計算。若 Q3 檔案不存在則移除 Q4 IS/CF，避免把全年值寫進 quarterly |
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

### 2026-04-17（Q4 EPS / 規則檔修正）

- 台股 `Q4` `basic_eps` / `diluted_eps` 改為單季值重建：
  - 優先：`Q4 EPS = FY EPS - 9M cumulative EPS`
  - fallback：若 cumulative EPS 不可得，才用 `Q4 EPS = FY EPS - Q1 EPS - Q2 EPS - Q3 EPS`
- 若 `9M cumulative EPS` 與 `Q1~Q3` 單季 EPS 都不可得，Q4 EPS 不寫入 quarterly facts，避免把全年值誤塞進 `Q4`
- `docs/financials-data-rules.md` 正式定義：
  - `financial_facts` 只放原始或可正確重建的 quarterly 值
  - `financial_metrics` 放 derived
  - `financials-view-schema.md` 專責 `key -> meaning/source` 字典

### 2026-04-16

**新標的 onboarding 修復**
- 問題：新 ticker 首次解析時，`financial_facts.ticker` 會被 `financial_companies` foreign key 擋住，導致 facts/metrics 全部寫入失敗
- 修法：`batch_parse.py` 在解析前會先從本地 iXBRL HTML 抽公司名稱，自動 upsert 一筆最小 `financial_companies` metadata
- 效果：像 `7769 鴻勁` 這類新台股標的可直接從本地 MOPS iXBRL 匯入 `Financials Viewer`

**缺前期檔案時的保守處理**
- 問題：缺少前期 YTD 檔案時，舊邏輯會把 `Q2/Q3` 的 CF YTD 或 `Q4` 的全年 IS/CF 直接寫入單季期別，造成 quarterly view 失真
- 修法：
  - `Q2/Q3` 若缺前一季，直接移除當期 CF，不再寫入 YTD
  - `Q4` 若缺 `Q3_FYxxxx`，直接移除該期 `IS/CF`，只保留正確的 `BS`
- 原則：沒有足夠前期檔案就拿掉，不硬填數字

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
