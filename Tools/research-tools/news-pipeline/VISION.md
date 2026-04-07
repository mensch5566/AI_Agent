# AI 投資智囊系統 — 終極目標與演進路線

記錄日期：2026-04-07

---

## 終極目標

**將 AI 練成公司投資決策的智囊**：能主動整理資訊、挑戰投資假設、追蹤判斷品質、隨時間持續進化的決策夥伴。

不是工具，是夥伴。

---

## 現在的起點：News Pipeline

新聞 pipeline 是第一塊磚。它做的事：

- Google News RSS → 語意去重 → 篩選 → thesis 影響分析 → 寫入 Supabase
- `filtering-rules.md` 積累篩選偏好，每次 pipeline 結束後蒸餾更新
- 摘要格式：事實層 + thesis 影響層（是否動搖投資觀點）

**核心限制（目前）**：
- 沉澱的是**偏好**，不是**智慧**
- 沒有 outcome feedback loop：系統不知道自己的判斷對不對
- 每次 pipeline 從零開始，Claude 推理能力本身不會因使用次數提升

---

## 演進路線

### 階段一（現在）：研究助理
- 過濾噪音、不漏掉重要消息
- 對每則新聞做 thesis 相關性判斷
- 偏好學習（filtering-rules.md 蒸餾）

### 階段二：開始學習
關鍵補充：**Outcome Tracking**

在 Supabase 建 `decision_log` 表：
```
date | ticker | thesis | action | outcome_date | outcome_result | notes
```
讓系統知道「我們看多 X → 後來發生了什麼」。
有了這個，才能回答「我們的判斷命中率是多少」、「哪類分析框架最有效」。

### 階段三：開始挑戰
關鍵補充：**反面證據 Pipeline**

每週跑一次「紅旗掃描」，對每個持倉標的主動搜尋：
- 為什麼這個 thesis 可能是錯的？
- 有沒有被我們忽略的反向信號？

不只確認你想聽的，而是主動找讓你不舒服的資訊。

### 階段四：開始綜合
關鍵補充：**跨標的關聯推理**

把多個 ticker 的訊號放在同一個 context 分析：
- 「NVDA capex 下修 + AVGO 砍單，對 TSM 代工量意味著什麼？」
- 每週出一份 portfolio-level 的訊號彙整，而不只是 ticker-level 的新聞

### 階段五：真正的智囊
以上全部到位 + 模型持續升版（Claude 4/5...）：
- 能替你把關投資假設
- 知道自己歷史上哪類判斷是有效的
- 主動提出你沒想到的關聯

---

## 關鍵洞察

**模型升版是免費的系統升級**：架構不需要改，Claude 每次升版，同樣的 pipeline、同樣的 filtering-rules.md，分析深度自動提升。

**最高 CP 值的下一步永遠是 outcome tracking**：在此之前，系統學的是偏好；在此之後，系統學的是有效性。這是從「研究助理」到「智囊」的分水嶺。

---

## 目前系統架構

```
NotebookLM（策略）
filtering-rules.md（蒸餾偏好）
        ↓
News Pipeline（每日）
  Step 0: 偵測新錄音
  Step 1: 讀投資策略
  Step 2: 讀篩選規則 + 新 raw feedback
  Step 3: RSS 抓取（raw URL，不解碼）
  Step 4: 去重 → 篩選 → thesis 影響摘要
  Step 4-4: 篩選後才解碼 URL（~20-30 篇，避免 429）
  Step 5: 寫入 Supabase news_archive
  Step 5.5: 蒸餾學習，更新 filtering-rules.md
  Step 6: 完成報告
        ↓
Supabase news_archive
        ↓
Command Center /api/news（前端讀取）
```

---

## 尚未建立的關鍵模組

| 模組 | 重要性 | 狀態 |
|------|--------|------|
| Outcome tracking（decision_log） | ★★★★★ | 未建立 |
| 反面證據 pipeline | ★★★★☆ | 未建立 |
| 跨標的關聯分析 | ★★★☆☆ | 未建立 |
| 宏觀 context 整合 | ★★★☆☆ | 未建立 |
