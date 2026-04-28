---
name: news-pipeline
description: 每日新聞 pipeline：從 NotebookLM 讀取投資策略、抓 Google News RSS 候選、依規則篩選，並將通過的新聞寫入資料庫。當用戶說 /news-pipeline、跑新聞、更新新聞時觸發。
---

# News Pipeline

這個 skill 用來執行個股新聞更新流程，核心目標是：

1. 讀取最新投資策略與篩選規則
2. 批量抓取各標的的 Google News RSS 候選
3. 去重、篩選、摘要與情緒標記
4. 將通過的新聞寫入 `news_archive`

## 主要檔案

- `Tools/research-tools/news-pipeline/fetch_rss.py`：抓取 Google News RSS 候選
- `Tools/research-tools/news-pipeline/tickers.json`：ticker / query / market 設定
- `Tools/research-tools/news-pipeline/filtering-rules.md`：篩選規則與分析視角
- `Tools/research-tools/news-pipeline/update-strategy.md`：策略更新流程
- `Tools/research-tools/news-pipeline/news-positive-feedback.md`：手動新增正回饋新聞
- `Tools/research-tools/news-pipeline/KNOWN_ISSUES.md`：已知限制
- `Tools/research-tools/news-pipeline/VISION.md`：長期設計目標

## 何時使用

當用戶提到以下需求時使用：

- 「跑新聞」
- 「更新新聞」
- 「news pipeline」
- 「整理今天新聞」
- 「幫我把新聞寫進 news archive」

## 執行流程

### Step 1: 讀策略與規則

先讀：

- 最新投資策略摘要 note
- `Tools/research-tools/news-pipeline/filtering-rules.md`

如果發現 NotebookLM 有新會議錄音但策略尚未更新，先詢問用戶是否要先跑策略更新，再繼續新聞流程。

### Step 2: 抓 RSS 候選

執行：

```bash
uv run --with feedparser,certifi python3 Tools/research-tools/news-pipeline/fetch_rss.py
```

輸出為 JSON array，每筆至少包含：

- `ticker`
- `title`
- `description`
- `url`
- `source`
- `date`

### Step 3: 去重與篩選

依照以下 context 進行篩選：

- 投資策略摘要
- `filtering-rules.md`
- `news_feedback` 裡的正負回饋
- 近 7 天 `news_archive` 既有資料

優先保留：

- 客戶訂單與產能決策
- 供需結構改變
- 政策 / 法規對產業影響
- 重大合作、競爭格局變化
- 財報、指引、管理層表態

排除：

- 純漲跌新聞
- 單純目標價調整
- 消費性開箱、促銷、規格比較
- 短線技術分析
- 重複報導

### Step 4: 生成入庫資料

每筆通過新聞整理為：

```json
{
  "date": "2026-03-11",
  "ticker": "MU",
  "headline": "Micron 宣布擴大 HBM3E 產能",
  "summary": "重點摘要",
  "analysis": "對 thesis 的影響",
  "url": "https://...",
  "source": "rss",
  "sentiment": "bullish"
}
```

### Step 5: 寫入與驗證

使用 Supabase service role 寫入 `news_archive`，並驗證：

- 預期筆數是否等於實際寫入筆數
- URL 是否正確
- headline / ticker 是否對應正確

## 注意事項

- 不要自行發明投資策略，策略內容必須來自 NotebookLM 或既有規則文件
- 對於策略中標記「待補充」的標的，篩選應偏寬鬆，不要自行加嚴
- `fetch_rss.py` 依賴網路，且 Google News 可能偶發失敗
- 如果要手動補一則好新聞，改走 `news-positive-feedback.md`

## 快速執行

若只是先確認 RSS 抓取是否正常，可先跑：

```bash
uv run --with feedparser,certifi python3 Tools/research-tools/news-pipeline/fetch_rss.py > /tmp/rss_candidates.json
```

再檢查輸出是否為有效 JSON。
