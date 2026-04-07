---
name: data-pipeline
description: Command Center 數據更新 pipeline：Market Indices + Dollar Volume + Economic Indicators，一次跑完所有資料源寫入 Supabase。當用戶說 /data-pipeline、「更新數據」、「跑 data」、「更新 command center」時觸發。
---

# Data Pipeline — Command Center 數據更新

批次更新 Command Center 的三個 Supabase 資料源：Market Indices、Dollar Volume、Economic Indicators (FRED)。

## 固定參數

- **Market script**: `Tools/research-tools/market-indices/fetch_market.py`
- **Dollar Volume script**: `Tools/research-tools/dollar-volume-screener/scripts/ingest_dv.py`
- **FRED script**: `Tools/research-tools/economic-data/fetch_fred.py`
- **環境變數**: `.env`（NEXT_PUBLIC_SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, FRED_API_KEY）

## 執行流程

### Step 1: Market Indices（~10 秒）

```bash
set -a; source /Users/mensch5566/AI_Agent/.env; set +a
uv run --with yfinance --with supabase python3 Tools/research-tools/market-indices/fetch_market.py
```

從 yfinance 拉取 5 檔 ETF（DIA, SPY, QQQ, IWM, UUP）報價，upsert 到 Supabase `market_indices`。

### Step 2: Dollar Volume（~2-3 分鐘）

```bash
set -a; source /Users/mensch5566/AI_Agent/.env; set +a
uv run --with finvizfinance --with yfinance --with pandas --with supabase python3 Tools/research-tools/dollar-volume-screener/scripts/ingest_dv.py
```

從 Finviz 拉 top 500 候選，yfinance 抓 10 天歷史，計算 1/5/10 天 dollar volume，top 50 per timeframe upsert 到 Supabase `dollar_volume`。

### Step 3: Economic Indicators（~30 秒）

```bash
set -a; source /Users/mensch5566/AI_Agent/.env; set +a
uv run --with requests --with supabase python3 Tools/research-tools/economic-data/fetch_fred.py
```

從 FRED API 抓取殖利率曲線、Fed Funds Rate、通膨（CPI/PCE YoY）、就業（NFP/失業率）、16 個 leading indicators、15 個 risk indicators。無 API 的指標保留既有值。結果以 JSONB upsert 到 Supabase `economic_data`。

**需要 `FRED_API_KEY`**：如果 `.env` 沒有此 key，Step 3 會跳過並提示。

### Step 4: 驗證

每個 step 跑完後確認 stdout 輸出沒有 ERROR。全部完成後輸出摘要：

```
✅ Data Pipeline 完成
   Market Indices: 5 indices updated
   Dollar Volume: 150 rows (50 × 3 timeframes)
   Economic Data: FRED 更新完成（X/16 leading, Y/15 risk indicators）
```

## 選擇性執行

用戶可以指定只跑部分：
- 「只更新 market」→ 只跑 Step 1
- 「只更新 dollar volume」→ 只跑 Step 2
- 「只更新經濟指標」→ 只跑 Step 3

## 注意事項

- **美股盤後跑最有價值**（ET 16:00 後 / TW 04:00 後），盤中資料會變動
- **Dollar Volume 最耗時**（500 支 yfinance download），其他都很快
- **FRED 資料多數月更/季更**，每週跑一次就夠，但跑了也不會怎樣
- 不需要 git push，資料已在 Supabase，前端透過 API route 動態讀取
