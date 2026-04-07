---
name: news-pipeline
description: 每日新聞 pipeline：從 NotebookLM 讀取投資策略 → Google News RSS 抓新聞 → Claude 語意去重+篩選 → 寫入 Supabase news_archive。當用戶說 /news-pipeline、「跑新聞」、「更新新聞」時觸發。
---

# News Pipeline — AI 新聞戰情系統

從 NotebookLM 讀取最新投資策略，結合 Supabase 回饋紀錄，透過 Google News RSS 抓取新聞，Claude 語意去重+篩選後寫入 Supabase `news_archive`，Command Center 透過 `/api/news` 動態讀取。

## 固定參數

- **NotebookLM 會議紀錄 notebook ID**: `a83bf056-1fdb-46e8-897f-4d5abd0ea704`
- **輸出目標**: Supabase `news_archive` table（upsert by URL）
- **Supabase API**: `/api/news-feedback`（GET 讀取回饋紀錄）
- **標的設定**: `Tools/research-tools/news-pipeline/tickers.json`（ticker、名稱、pool、market、RSS query 統一維護）

## 執行流程

### Step 0: 偵測新會議錄音 & 提示更新策略

在跑新聞之前，先檢查是否有新的會議錄音需要同步策略：

1. 用 `mcp__notebooklm-mcp__source_list_drive` 列出所有 source
2. 用 `mcp__notebooklm-mcp__note` 讀取策略摘要 note（ID: `47d23812-c892-4133-8f6b-61a4238df00b`），取得「最後更新」日期
3. 比對 source title 中的日期（格式如 `2026-01-23-共學-早上.m4a`）是否有 > 最後更新日期的
   - **沒有新 source** → 跳過，直接進入 Step 1
   - **有新 source** → 通知用戶有新錄音，詢問是否要先更新策略。**用戶確認後**才執行 `Tools/research-tools/news-pipeline/update-strategy.md` 的完整流程。用戶也可以選擇跳過，直接用現有策略繼續跑新聞。

### Step 1: 讀取投資策略

用 `mcp__notebooklm-mcp__note` 讀取策略摘要 note（ID: `47d23812-c892-4133-8f6b-61a4238df00b`）的完整內容，作為後續搜尋與篩選的 context。

**注意**：直接讀 note 內容即可，不需要再 query 一次 NotebookLM。策略摘要 note 就是最新的。

### Step 2: 讀取篩選規則 + 分析視角

**2-1. 讀取蒸餾後的規則文件**（主要 context）

讀 `Tools/research-tools/news-pipeline/filtering-rules.md`，取得：
- 篩選規則：哪類新聞要 / 不要
- 分析視角：用戶關注的策略顧慮 / 紅旗信號（用於 Step 4 摘要）
- 最後蒸餾時間戳（用於下一步的 cutoff）

**2-2. 讀取新增 raw feedback**（補充 context）

只讀「上次蒸餾時間戳之後」的新回饋：

```bash
curl -s "https://putemxomuepwudtbhesd.supabase.co/rest/v1/news_feedback?select=*&order=created_at.desc&limit=20&created_at=gt.<LAST_DISTILL_TS>" \
  -H "apikey: <SUPABASE_ANON_KEY>"
```

**如果 `filtering-rules.md` 不存在或尚未蒸餾**：讀近 50 筆 raw feedback 作為替代。

整理成兩類 context：
- negative 回饋 → 補充篩選排除規則
- positive 回饋中的觀點 → 補充分析視角

### Step 3: 抓取 Google News RSS

用 Python 腳本批量抓取所有標的的 Google News RSS（過去 24 小時）：

```bash
uv run --with feedparser,certifi python3 Tools/research-tools/news-pipeline/fetch_rss.py
```

腳本讀取 `tickers.json`，每個 ticker 有公司短名作為搜尋 query，台股標的自動切換 `zh-TW` locale。
輸出為 JSON array，每筆包含 `ticker`, `title`, `description`, `url`, `source`, `date`。

**如果腳本失敗**：檢查 stderr 的 WARN 訊息，個別 ticker 失敗不影響其他。

> **TODO**：加入頭部媒體 URL 掃描（`news-sources.json` 的 `official` 清單），與 RSS 合併候選清單。

### Step 4: 語意去重 + 篩選

拿到 RSS 候選清單後，執行以下具體步驟：

#### 4-1. 將 RSS 輸出存檔並提取 title 列表

RSS 候選通常有 500-900 則，不可能全部丟進 context。用 Python 提取 `ticker + title + source`，按 ticker 分組印出：

```bash
python3 -c "
import json
from collections import defaultdict
data = json.load(open('/tmp/rss_candidates.json'))
by_ticker = defaultdict(list)
for item in data:
    by_ticker[item['ticker']].append(item)
for ticker, items in sorted(by_ticker.items()):
    print(f'\n=== {ticker} ({len(items)} items) ===')
    for i, item in enumerate(items):
        print(f'{i+1}. [{item[\"date\"]}] {item[\"title\"]} ({item[\"source\"]})')
"
```

這樣只需要看 title 就能判斷，不需要讀 description（Google News RSS 的 description 只是 HTML 包裹的重複 title，沒有額外資訊）。

#### 4-2. 拉取 Supabase 既有新聞

```bash
set -a; source /Users/mensch5566/AI_Agent/.env; set +a
uv run --with supabase python3 -c "
from supabase import create_client
import os, json
sb = create_client(os.environ['NEXT_PUBLIC_SUPABASE_URL'], os.environ['SUPABASE_SERVICE_ROLE_KEY'])
from datetime import date, timedelta
cutoff = (date.today() - timedelta(days=7)).isoformat()
res = sb.table('news_archive').select('id, headline, url, ticker, date').gte('date', cutoff).execute()
json.dump(res.data, __import__('sys').stdout, ensure_ascii=False, indent=2)
"
```

#### 4-3. 逐 ticker：去重 → 篩選 → 分析摘要

對每個 ticker，一次完成三個動作：

**① 去重**（根據 title 語意）：
- 同一事件多家報導 → 只留一則（優先更詳細或來源更好的）
- 對比 news_archive 既有 headline → 已入庫的同一事件不重複寫入
- 後續發展（follow-up）→ **不是重複**，保留並記錄 `parent_id`

**② 篩選**（按優先順序，結合 Step 2 的蒸餾規則）：
1. ✅ 與持倉標的 thesis 或關注重點直接相關
2. ✅ 涉及基本面變化（營收、產能、供需、客戶、政策）
3. ✅ 產業結構性變化（新技術、併購、法規）
4. ❌ 純股價漲跌報導（無基本面分析）
5. ❌ 短線技術分析 / 投機建議
6. ❌ 符合 `filtering-rules.md` 排除規則的新聞
7. ❌ 產品開箱、零售促銷、硬體規格列表等噪音

**判斷情緒**：
- `bullish`：對該標的的投資 thesis 有正面支撐
- `bearish`：對該標的的投資 thesis 有負面影響
- `neutral`：重要資訊但方向不明確

**③ 摘要撰寫**（核心新增）：

`headline` = 中文標題，簡短描述事件
`summary` = 事實層（1-2 句）：發生了什麼
`analysis` = 影響分析層（1-2 句）：這則新聞是否動搖/支撐我們的投資觀點

`analysis` 要回答的問題：
- 這個消息印證了我們持有的理由，還是挑戰了它？
- 有沒有觸發 `filtering-rules.md` 裡記錄的策略顧慮或紅旗？
- 需要繼續追蹤什麼？

**輸出範例**：
```
headline: Micron HBM3E 出貨量 Q2 超預期，市佔持續擴大
summary: Micron 公布 Q2 HBM3E 出貨量季增 40%，超越市場預期，並確認主要 AI 客戶訂單能見度延伸至 2026 Q4。
analysis: 印證 AI memory demand 加速的核心假設，支撐 HBM 供不應求的 thesis。需關注 SK Hynix 下週法說是否提出反制說法。
```

**每則保留的新聞輸出格式**：
```
ticker: NVDA
rss_title_fragment: "Nvidia announces"   ← 原始英文 RSS title 的前 3-5 個關鍵詞，供 Step 4-4 比對用
headline: （中文標題）
summary: （中文摘要）
sentiment: bullish/bearish/neutral
```

**⚠️ 關鍵規則**：`rss_title_fragment` 必須來自 RSS JSON 的原始英文 title，**不能是 Claude 自己生成的中文 headline**。如果一則中文 headline 是合併多個 RSS 事件生成的（無對應單一 RSS 條目），必須拆成多則分別處理，或放棄寫入。

**排除的新聞也要記錄原因**（給 Step 5.5 蒸餾用）：
列出「哪幾則被排除、排除理由」，格式：`[REJECT] {ticker}: {title_fragment} — 原因`

#### 4-4. 配回 URL

`fetch_rss.py` 已在抓取時把 URL 轉換為 `news.google.com/articles/{base64}`，在瀏覽器中會直接 redirect 到原始來源，**不需要任何解碼步驟**。

用 Step 4-3 記錄的 `rss_title_fragment`（英文）配回 URL：

```bash
python3 -c "
import json
data = json.load(open('/tmp/rss_candidates.json'))
selected = [('TICKER', 'english rss title fragment'), ...]  # 填入 Step 4-3 記錄的英文 fragment
for ticker, fragment in selected:
    matched = next((item for item in data if item['ticker'] == ticker and fragment in item['title']), None)
    if matched:
        print(f'{ticker}: {matched[\"url\"]}')
    else:
        print(f'[WARN] No match: {ticker} | {fragment}')
"
```

**注意**：
- fragment 必須是**英文原始 title** 的一部分，不是中文 headline
- title 中的特殊字元（引號、撇號、$）可能導致比對失敗，改用 `in` 部分匹配
- **禁止手打 URL**，一律用 Python 從 RSS JSON 配回
- 若確實找不到對應的單一 RSS 條目（headline 是合成的），該則新聞**不寫入**，重新回到 4-3 拆分處理

### Step 5: 寫入 Supabase news_archive

將篩選結果 upsert 到 Supabase `news_archive` table。

**寫入方式**：用 Python + supabase-py，透過 `uv run` 執行：

```bash
set -a; source /Users/mensch5566/AI_Agent/.env; set +a
uv run --with supabase python3 -c "
from supabase import create_client
import os, json

sb = create_client(os.environ['NEXT_PUBLIC_SUPABASE_URL'], os.environ['SUPABASE_SERVICE_ROLE_KEY'])

items = json.loads('''<JSON_ARRAY>''')

for item in items:
    sb.table('news_archive').upsert(item, on_conflict='url').execute()
"
```

每筆 item 的格式：
```json
{
  "date": "2026-03-11",
  "ticker": "MU",
  "headline": "Micron 宣布擴大 HBM3E 產能",
  "summary": "Micron 將投資 XX 億美元擴大 HBM3E 產線，預計 2026 Q4 量產...",
  "analysis": "印證 AI memory demand 加速的核心假設，支撐 HBM 供不應求的 thesis。",
  "url": "https://...",
  "source": "rss",
  "sentiment": "bullish"
}
```

**source 欄位值**：`rss`（Google News RSS）、`official`（官方 IR 頁面）、`manual`（手動新增）

**parent_id**：如果是 follow-up 新聞，從既有資料中找到原始新聞的 UUID，設定 `parent_id`。

#### 5-2. 驗證寫入結果

寫完後，比對「篩選通過的清單」和「實際入庫的結果」：

```bash
set -a; source /Users/mensch5566/AI_Agent/.env; set +a
uv run --with supabase python3 -c "
from supabase import create_client
import os, json
sb = create_client(os.environ['NEXT_PUBLIC_SUPABASE_URL'], os.environ['SUPABASE_SERVICE_ROLE_KEY'])
from datetime import date, timedelta
cutoff = (date.today() - timedelta(days=1)).isoformat()
res = sb.table('news_archive').select('headline, ticker, url').gte('date', cutoff).execute()
print(f'Today in DB: {len(res.data)} items')
for r in res.data:
    print(f'  {r[\"ticker\"]}: {r[\"headline\"][:50]}')
"
```

**驗證步驟**：

**A. 數量驗證**：
1. 計算預期寫入數量（Step 4 篩選通過的總數）和實際 DB 數量，兩者必須一致
2. 如果有差異，列出遺漏的 headline，逐一排查原因（URL 配對失敗、特殊字元、upsert 錯誤）
3. 遺漏的項目必須修正後重新寫入，不可放棄

**B. URL 正確性驗證**：
逐一檢查每則新聞的 headline 與 URL 是否對得上（URL 的域名和路徑是否合理對應 headline 的內容）。

```bash
set -a; source /Users/mensch5566/AI_Agent/.env; set +a
uv run --with supabase python3 -c "
from supabase import create_client
import os
sb = create_client(os.environ['NEXT_PUBLIC_SUPABASE_URL'], os.environ['SUPABASE_SERVICE_ROLE_KEY'])
from datetime import date, timedelta
cutoff = (date.today() - timedelta(days=1)).isoformat()
res = sb.table('news_archive').select('id, ticker, headline, url').gte('date', cutoff).execute()
for r in res.data:
    print(f'{r[\"ticker\"]} | {r[\"headline\"][:45]}')
    print(f'  {r[\"url\"][:100]}')
    print()
"
```

肉眼掃一遍：URL 路徑裡的關鍵字是否與 headline 內容相符。如果 URL 明顯不對（例如 LEU 新聞指向 TSM 文章），說明 Step 4-4 配回 URL 時配錯了。

**修復方式**：從 RSS JSON (`/tmp/rss_candidates.json`) 重新用 title fragment 搜尋正確 URL，然後 update Supabase。

**常見問題**：
- URL 配對失敗（特殊字元）→ 改用 `in` 部分匹配
- **禁止手打 URL**，一律用 Python 從 RSS JSON 配回

### Step 5.5: 蒸餾學習（更新 filtering-rules.md）

每次 pipeline 結束後，把這次的決策和 raw feedback 提煉回 `filtering-rules.md`。

**輸入材料**：
1. 這次 Step 4-3 記錄的 `[REJECT]` 清單（排除原因）
2. 這次篩選通過的新聞（accept 理由隱含在選擇中）
3. Step 2-2 讀進來的新增 raw feedback
4. 現有的 `filtering-rules.md` 內容

**執行**：讀現有規則 + 上方材料，輸出更新後的整份 `filtering-rules.md`：
- 合併語意相近的規則（不要讓清單無限膨脹）
- 刪除被反例推翻的規則
- 新增這次發現的新模式（要有足夠的 evidence，不要因為一個案例就加規則）
- 更新時間戳

**寫入**：
```bash
# 直接覆蓋更新（內容由 Claude 輸出後用 Write tool 寫入）
Tools/research-tools/news-pipeline/filtering-rules.md
```

**原則**：
- 規則要可操作（「不要純股價漲跌」比「不要噪音」好）
- 分析視角要具體（「關注 HBM 競爭格局變化」比「關注競爭」好）
- 寧可規則少而精，不要多而雜

### Step 6: 完成報告

輸出簡短摘要：
```
✅ 新聞更新完成（2026-03-11）
   RSS 候選 X 則 → 去重+篩選後 Y 則 → 實際寫入 Z 則
   標的覆蓋：MU(3), NVDA(2), AMZN(1)...
   遺漏：0 則（或列出遺漏項目及原因）
```

不需要 git push（資料已在 Supabase，前端透過 `/api/news` 動態讀取）。

## 注意事項

- **如果 NotebookLM 查詢失敗**：用上次的策略摘要 note 繼續跑，不要中斷
- **如果某個標的搜不到相關新聞**：跳過，不要硬湊
- **新聞語言**：英文為主（來源是英文財經媒體），summary 用中文撰寫
- **RSS 腳本**：`Tools/research-tools/news-pipeline/fetch_rss.py`
- **標的設定**：`Tools/research-tools/news-pipeline/tickers.json`
