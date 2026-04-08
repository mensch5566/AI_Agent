# parse-twse-ixbrl — 台股 XBRL 財務數據解析

用於解析台灣股票交易所 (TWSE) 的 Inline XBRL (iXBRL) 財務報表，自動提取關鍵指標並驗證數據。

## 使用方式

```
/parse-twse-ixbrl <ticker> [file_path]
```

## 參數

- **ticker** (必須)：股票代碼，如 `2454` (聯發科)
- **file_path** (可選)：XBRL 文件路徑。若不提供，會提示用戶指定或自動查找下載目錄

## 工作流程

### Step 1: 驗證輸入
- 檢查 ticker 格式（4 位數）
- 確認 XBRL 文件存在
- 若文件不存在，提示用戶從 TWSE 下載：
  ```
  https://mopsov.twse.com.tw/server-java/t164sb01?step=1&CO_ID=<ticker>&SYEAR=2025&SSEASON=4
  ```

### Step 2: 解析 iXBRL
- 用 lxml 解析 HTML 中的表格
- 從資產負債表、損益表、現金流量表提取指標：
  - **資產負債表**：流動資產、總資產、流動負債、總負債、權益
  - **損益表**：營業收入、營業毛利、營業利益、稅前利潤、淨利
  - **現金流量**：營業現金流、投資現金流、融資現金流

### Step 3: 與 Supabase 比對
- 查詢 financial_facts 表中該 ticker 的最新期別數據
- 自動處理單位差異（XBRL 用基本單位，Supabase 用千位）
- 輸出匹配/不匹配的統計

### Step 4: 輸出驗證報告
```
✅ 驗證成功：5 項匹配
❌ 需調查：2 項不匹配
ⓘ 未找到：1 項指標
```

## 範例

**用法 1：指定文件路徑**
```
/parse-twse-ixbrl 2454 /Users/mensch5566/Downloads/tifrs-fr1-m1-ci-cr-2454-2025Q4.html
```

**用法 2：自動查找下載目錄**
```
/parse-twse-ixbrl 2454
```
（會自動在 `~/Downloads` 中尋找該 ticker 的最新 XBRL 文件）

## 輸出

- 列出所有提取的指標及數值
- 與 Supabase 的比對結果
- 驗證統計（匹配數、差異數、未找到數）
- 如有單位不匹配，自動提示需轉換

## 注意事項

- 首次使用前需確保 `scripts/parse_twse_ixbrl.py` 存在
- Supabase 連線需要有效的 API key（已配置在環境變數）
- XBRL 檔案通常在公司年報公佈後 2-3 天上線 TWSE 網站
- 單位轉換：XBRL 基本單位 ÷ 1,000 = Supabase 千位單位

## 實作細節

**Python 脚本** (`parse_ixbrl.py`)：
- 自動化參數化 XBRL 解析
- 從 HTML 表格提取財務數據
- 與 Supabase 自動比對並驗證
- 支持單位轉換（XBRL 基本單位 → Supabase 千位單位）
- 優先匹配中文標籤（避免英文歧義）

**入口點** (`run.sh`)：
- 簡單的 bash 包裝，調用 Python 脚本
- 支援直接傳遞參數

## 驗證結果示例

```
✅ 5 個匹配（資產負債表）
❌ 2 個差異（損益表）
ⓘ 1 個未找到（指標不在 DB）
```

## 後續改進方向

- [ ] 自動從 TWSE API 下載最新 XBRL 文件
- [ ] 支援多家公司批量解析
- [ ] 匯出驗證報告為 CSV/Excel
- [ ] 建立 XBRL 歷史追蹤表
- [ ] 添加更多財務指標到 Supabase 的 financial_facts 表
