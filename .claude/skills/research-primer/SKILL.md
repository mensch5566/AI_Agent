---
name: research-primer
description: 新標的 Company Primer：NotebookLM 結構化提問 → Perplexity 技術深潛 → 整合輸出。當用戶說 /research-primer、「跑 primer」、「研究新標的」時觸發。
---

# Research Primer — 新標的快速研究

從 NotebookLM 讀取 SEC 財報與 Earnings Call Transcripts，一次跑完 Phase 2→3→4，輸出完整的 Company Primer。

## 前置條件

用戶需先完成 Phase 1（手動）：
- 在 NotebookLM 建立該標的的 notebook（命名：`{Company Name} - {TICKER}`）
- 放入 SEC 10-K、10-Q、Earnings Call Transcripts 等資料

## 執行方式

```
/research-primer {TICKER}
```

例如：`/research-primer SNDK`

## 執行流程

全程不中斷，一路跑完。

### Step 1：找到 NotebookLM Notebook

1. 用 `mcp__notebooklm-mcp__notebook_list` 列出所有 notebook
2. 找到 title 包含 `{TICKER}` 的 notebook
3. 如果找不到 → 提示用戶先建立 notebook 並放入資料，結束

### Step 2：結構化提問（Phase 2 — 5 個固定問題）

依序用 `mcp__notebooklm-mcp__notebook_query` 對該 notebook 提問。每個問題獨立發送，收集完整回覆。

**Q1 — 業務拆解**
```
請根據財報和 earnings call transcript 回答：
公司有哪幾個業務線（segment）？各自營收佔比多少？哪些在成長、哪些在衰退？
請列出最近一季各 segment 的：
- 營收金額
- 營收佔比（%）
- YoY 變化（%）
- QoQ 變化（%）
用表格呈現。
```

**Q2 — 產品與技術棧**
```
請根據財報和 earnings call transcript 回答：
公司的核心產品是什麼？製造流程或技術架構是什麼？
有哪些世代演進（如製程節點、產品代號）？目前最新一代是什麼？
請按產品線分別說明。
```

**Q3 — 術語清單**
```
請根據最近 2-3 季的 earnings call transcript 回答：
管理層反覆提到哪些技術術語和產品代號？
請列出每個術語並用一句話解釋其含義和重要性。
格式：
- {術語}：{一句話解釋}
至少列出 10 個最重要的術語。
```

**Q4 — 競爭格局**
```
請根據財報和 earnings call transcript 回答：
管理層怎麼描述競爭對手和市場格局？公司的差異化優勢在哪？
市佔率大約多少？主要競品是誰？
如果有提到具體的競爭對手名字，請列出。
```

**Q5 — 成長驅動力與風險**
```
請根據財報和 earnings call transcript 回答：
管理層認為未來 1-2 年的成長來自哪裡？
有哪些明確提到的 tailwind（順風）和 headwind（逆風）？
資本支出（CapEx）計畫是什麼？金額多少？投向哪些領域？
```

### Step 3：技術深潛（Phase 3）

對 Q3 輸出的術語清單，用 `mcp__perplexity__perplexity_search` 搜尋技術解釋。

**搜尋策略**：將相關術語分組搜尋（每次 2-3 個相關術語），避免逐個搜浪費 API。通常 3-4 組即可覆蓋所有術語。

**每組搜尋的 query 範本**：
```
"{術語1} {術語2} technology explained how it works {產業關鍵字}"
```

**參數**：
- `max_results`: 5
- 不需要 `recency` 參數（技術原理不限時間）

對每個術語整理出：
- **原理**：2-3 句話解釋底層技術（假設讀者有基礎科技知識但不是該領域專家）
- **產業定位**：是主流？領先？落後？
- **世代演進**：如果有（如 BiCS6 → BiCS7 → BiCS8），說明每一代的關鍵提升

搜不到的術語直接用 Phase 2 的解釋，不要硬搜。

### Step 4：整合輸出（Phase 4 — Company Primer）

將 Phase 2 + Phase 3 整合為最終的 Company Primer，格式如下：

```markdown
# {TICKER} Company Primer

## 1. 公司概覽
{1 段話，描述公司做什麼、核心業務、規模}

## 2. 業務線拆解
{表格：segment / 營收 / 佔比 / YoY / QoQ / 關鍵產品}
{補充說明各 segment 的趨勢}

## 3. 核心技術
{每個關鍵術語的詳細解釋，融合 Phase 2 的業務 context + Phase 3 的技術原理}
{包含：原理、產業定位、世代演進}

## 4. 競爭格局
{競爭對手表格 + 差異化優勢分析}

## 5. 成長與風險
{Tailwinds / Headwinds / CapEx}

---
來源：NotebookLM notebook "{notebook title}" + Perplexity 技術搜尋
生成日期：{YYYY-MM-DD}
```

**語言**：中文
**風格**：簡潔、數據驅動、避免主觀判斷

### Step 5：儲存

1. 將完整 Company Primer 顯示給用戶
2. 存檔至 `public/data/equity-research/primers/{TICKER}_primer.md`

## 注意事項

- **NotebookLM 帳號**：使用 work profile（green@khouse.com.tw），個股 notebook 都在這個帳號下
- **Perplexity API 要省著用**：術語搜尋分組進行，3-4 組打完，不要逐個搜
- **不要自行推測**：業務/財務資訊必須來自 NotebookLM 回覆（= 財報/transcript），技術解釋來自 Perplexity
- **保留引用來源**：NotebookLM 回覆中如有 [1] [2] 等引用標記，保留在輸出中
- **如果 NotebookLM 查詢失敗**：提示用戶檢查 notebook 是否存在且有足夠資料
- **全程不中斷**：不要在中間步驟停下來問用戶，一路跑完 Phase 2→3→4
