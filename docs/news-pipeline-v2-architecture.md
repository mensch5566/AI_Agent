# News Pipeline v2 架構草案

更新日期：2026-04-13

## 目的

保留這份草案，作為後續重構 `news-pipeline` 的設計基礎。

這次先記錄方向，不直接開發。

---

## 背景問題

現行 `news-pipeline` 的主要痛點不是「抓不到新聞」，而是：

1. **候選來源便宜但雜訊太多**
   - Google News RSS 很容易混入地名、討論串、盤勢文、舊文重發。
   - 例如 `GLW` / `Corning` 會抓到地方新聞；`聯發科` 會抓到舊文被重新聚合的 `討論牆` 條目。

2. **規則越修越多，維護成本持續上升**
   - 每修一個例外，往往只是解掉單一 case。
   - ticker / query 一多，規則會迅速失控。

3. **目前的問題本質上是 relevance ranking，不是單純抓取問題**
   - 我們真正需要的是「哪些新聞值得留」
   - 而不是「怎麼把所有新聞都抓進來」

---

## 核心判斷

### 不建議：整條 pipeline 全丟給 Perplexity

理由：

- Perplexity 擅長問答、摘要、研究補強，不一定適合當唯一穩定收集器
- 若完全交給 Perplexity，常見問題會變成：
  - 每次結果不完全一致
  - coverage 不穩
  - 難以 deterministic 去重
  - 不易驗證「今天是不是漏了重要新聞」
  - 大量 ticker 每日執行成本偏高

### 建議：Hybrid 架構

把任務拆成三段：

1. **Collector**：便宜、穩定地抓候選
2. **Semantic Ranker**：用模型判斷相關性與重要性
3. **Writer**：只把高信號結果寫入 `news_archive`

也就是：

> RSS / feeds 負責「廣泛抓」
> LLM / Perplexity 負責「聰明判斷」

而不是讓單一模型同時負責「搜尋、判斷、去重、入庫」。

---

## v2 設計目標

### 功能目標

- 降低規則數量
- 降低舊文、聚合文、地名歧義造成的雜訊
- 保留可重跑、可驗證、可追蹤的 pipeline 特性
- 讓 `news_archive` 的品質穩定提升

### 工程目標

- Collector 與 Ranker 解耦
- Prompt / schema 固定化
- 模型可替換（Claude / GPT / Perplexity 不綁死）
- 每一層都能單獨 debug

---

## 建議架構

## Layer 1：Candidate Collector

### 職責

只負責收集「候選新聞」，不做深度判斷。

### 建議來源

- Google News RSS
- 官方 IR / Press Release 頁面
- 少量高品質媒體來源（可後續增補）

### 這層只保留極小規則

只做明顯垃圾排除：

- `討論牆 |`、論壇聚合文
- 明顯非公司主體的地方新聞
- 完全重複 URL
- feed 時間明顯過舊

### 不要在這層做的事

- 不要寫太多 ticker-specific if/else
- 不要在這層做最終 relevance 判斷
- 不要在這層直接寫入 `news_archive`

### 輸出格式

建議輸出到 `tmp` 或 staging 檔案：

```json
{
  "ticker": "SNDK",
  "title": "SanDisk 受惠 AI 需求與 NAND 價格順風，記憶體熱度延續",
  "url": "https://...",
  "source": "AOL.com",
  "published_at": "2026-04-12T00:00:00Z",
  "collector": "google_rss",
  "raw_summary": "..."
}
```

---

## Layer 2：Semantic Ranker

### 職責

這層才是 v2 的核心。

模型根據：

- ticker 對應 thesis
- 既有篩選原則
- 近 7 天既有新聞
- feedback 歷史

判斷每則候選是否值得保留。

### 可用模型

- Claude
- GPT
- Perplexity

### 對 Perplexity 的定位

Perplexity 適合作為：

- relevance / novelty 判斷器
- article summary 補強器
- 「今天可能漏掉的重大新聞」補抓器

Perplexity 不建議作為：

- 唯一 candidate source
- 唯一 truth source

### 建議輸出 schema

每筆候選都要求模型輸出固定 JSON：

```json
{
  "ticker": "SNDK",
  "url": "https://...",
  "is_relevant": true,
  "relevance_score": 0.92,
  "novelty_score": 0.81,
  "thesis_impact": "supports_nand_supply_demand_thesis",
  "sentiment": "bullish",
  "summary": "一段中文摘要",
  "analysis": "一段中文投資意義分析",
  "reason": "為什麼留下這篇"
}
```

### 最重要的不是單一 label，而是這三件事

- **相關性**：跟 ticker thesis 有沒有關
- **新意**：是不是重複敘事
- **重要性**：有沒有改變投資判斷或 KPI 追蹤

---

## Layer 3：DB Writer

### 職責

只接收已經過 ranker 判定的高信號結果。

### 入庫邏輯

- `relevance_score >= threshold`
- `novelty_score >= threshold`
- URL 不重複
- headline 與近 7 天事件不屬於同一個低價值重複報導

### 寫入欄位

維持現有 `news_archive` 主結構即可：

- `date`
- `ticker`
- `headline`
- `summary`
- `analysis`
- `url`
- `source`
- `sentiment`
- `parent_id`

### 建議新增的延伸欄位（未必要立刻做）

- `collector`
- `relevance_score`
- `novelty_score`
- `ranker_model`
- `ranker_reason`
- `run_id`

這樣之後比較容易 audit。

---

## 建議流程圖

```text
[Ticker Config / Thesis / Feedback]
               |
               v
      [Candidate Collector]
               |
               v
      candidate_news.json
               |
               v
       [Semantic Ranker]
               |
      +--------+--------+
      |                 |
      v                 v
[accepted.json]   [rejected.json]
      |
      v
         [DB Writer]
      |
      v
      news_archive
```

---

## v2 的規則哲學

### 原則

**規則不是主系統，只是 guardrail。**

應保留：

- 少數高確定性的垃圾排除規則
- 明確的資料完整性檢查
- deterministic 的 dedupe

應移除：

- 大量 case-by-case 的標題黑名單
- 太多 ticker-specific 特判
- 把業務判斷硬編成 if/else

### 判斷責任分配

- Collector：拿到夠多候選
- LLM：判斷 relevance / novelty / impact
- DB Writer：保證資料乾淨寫入

---

## Perplexity 在 v2 的三種可選角色

### Option A：不用 Perplexity

使用 Claude / GPT 做 ranker。

適合：

- 想降低外部依賴
- 想維持單一模型工作流

### Option B：Perplexity 當 Ranker

Collector 仍用 RSS，Perplexity 只負責判斷與補摘要。

適合：

- 想提升語意篩選品質
- 願意接受較高 token / API 成本

### Option C：Perplexity 當「補漏器」

先跑 RSS + ranker，再額外問：

> 今天這些 ticker 有沒有 RSS 沒抓到、但值得注意的重大新聞？

適合：

- 需要高覆蓋率
- 但不想讓 Perplexity 成為主 pipeline

### 目前最推薦

**Option B 或 C**，不推薦 full Perplexity only。

---

## 建議的 prompt 思路

ranker prompt 應固定要求模型做四件事：

1. 判斷新聞主體是不是目標公司 / 產業鏈相關主體
2. 判斷是否與 thesis / KPI / 風險追蹤直接相關
3. 判斷是否只是舊敘事重複
4. 產出固定 JSON，不要自由發揮

### 關鍵要求

- 不要只看標題語氣
- 要以投資 thesis 相關性判斷
- 不可把純盤勢、目標價、論壇聚合文當成高價值新聞

---

## 建議的執行模式

### Mode 1：Daily Auto

- 每日自動跑
- 門檻較高
- 低信心結果不入庫

### Mode 2：Analyst Review

- 候選跑完後產出 shortlist
- 由人確認後再寫入

### Mode 3：Deep Research

- 針對單一 ticker 追加 Perplexity / 其他模型深挖
- 用於週報或月報前人工加強

---

## 遷移建議

### Phase 1：不改資料表，先重構流程

- 保留 `news_archive`
- 保留 `tickers.json`
- 保留 `feedback`
- 先把流程拆成：collector / ranker / writer

### Phase 2：引入 staging outputs

- `tmp/candidates.json`
- `tmp/accepted.json`
- `tmp/rejected.json`

### Phase 3：若品質穩定，再加 metadata 欄位

- `relevance_score`
- `novelty_score`
- `run_id`
- `ranker_model`

---

## 成功指標

重構後應觀察這些指標：

1. 每日候選數是否穩定
2. 最終入庫數是否合理
3. 垃圾新聞比例是否下降
4. 舊文重發 / 聚合文是否顯著減少
5. 週報與前端使用時，人工修正量是否下降

---

## 暫定結論

### 方向

`news-pipeline v2` 不應再持續堆規則。

應改為：

- **收集層便宜、廣泛、簡單**
- **判斷層由模型主導**
- **規則層只保留最小 guardrail**

### 對 Perplexity 的結論

Perplexity 可以成為 v2 的重要組件，
但更適合做：

- semantic ranking
- summary / analysis 補強
- 重大新聞補漏

不建議讓它成為唯一的新聞收集器。

---

## 後續可做事項

- 定義 `accepted / rejected` 的固定 JSON schema
- 寫一版 ranker prompt v1
- 決定 ranker 用 Claude、GPT、Perplexity 還是混合
- 評估是否需要 `news_pipeline_runs` 或 staging table
- 決定 `review queue` 要放檔案還是資料表

