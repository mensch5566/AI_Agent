---
name: news-positive-feedback
description: 手動新增正回饋新聞。當用戶說 /news-positive-feedback、「這則新聞很好」、「正回饋」時觸發。
---

# News Positive Feedback — 手動正回饋

用戶提供一則好新聞的 URL 和說明，AI 抓取新聞內容、整理後寫入 Supabase 作為正回饋，供 `/news-pipeline` 篩選時參考。

## 執行流程

### Step 1: 取得新聞資訊

用戶提供：
- **URL**（必填）
- **相關標的**（必填，可多個）
- **為什麼這則新聞好**（必填，用戶口述即可）

如果用戶只給 URL，用 WebFetch 抓取 headline 和日期，再請用戶補充標的和原因。

### Step 2: WebFetch 抓取新聞

用 WebFetch 取得：
- 原始 headline（英文）
- 發布日期
- 關鍵內容摘要

### Step 3: 整理並寫入 Supabase

對每個相關標的，分別 POST 一筆到 Supabase：

```bash
curl -s "https://putemxomuepwudtbhesd.supabase.co/rest/v1/news_feedback" \
  -H "apikey: <SUPABASE_ANON_KEY>" \
  -H "Authorization: Bearer <SUPABASE_ANON_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "positive",
    "ticker": "<TICKER>",
    "headline": "<英文原始 headline>",
    "url": "<URL>",
    "sentiment": "bullish|bearish|neutral",
    "reason": "<中文，結合用戶說明與新聞內容，說明為什麼這則新聞對該標的的投資敘事有價值>",
    "created_by": "cli"
  }'
```

**reason 撰寫原則**：
- 用中文
- 連結到該標的的投資 thesis（從策略摘要中理解）
- 說明這則新聞為什麼重要、影響什麼敘事
- 參考用戶的口述說明，但補充結構化的投資邏輯

### Step 4: 確認

列出寫入的記錄，讓用戶確認。

## 注意事項

- **sentiment 判斷**：根據新聞對該標的投資 thesis 的影響判斷，不是新聞本身的語氣
- **一則新聞可對應多個標的**：分別寫入，reason 針對各標的的 thesis 分別撰寫
- **SUPABASE_ANON_KEY**：從 .env 讀取（`NEXT_PUBLIC_SUPABASE_ANON_KEY`）
- **created_by 固定為 "cli"**：區分來源（web = 前端負回饋，cli = 手動正回饋）
