---
name: update-strategy
description: 偵測 NotebookLM 會議紀錄是否有新 source，有的話自動更新投資策略摘要 note。當用戶說 /update-strategy、「更新策略」時觸發。
---

# Update Strategy — 投資策略同步

偵測 NotebookLM「會議紀錄」筆記本是否有新的會議錄音，如果有，從錄音內容萃取投資策略變化並更新策略摘要 note。

## 固定參數

- **NotebookLM 會議紀錄 notebook ID**: `a83bf056-1fdb-46e8-897f-4d5abd0ea704`
- **策略摘要 note ID**: `47d23812-c892-4133-8f6b-61a4238df00b`

## 執行流程

### Step 1: 偵測新 source

1. 用 `mcp__notebooklm-mcp__source_list_drive` 列出所有 source
2. 用 `mcp__notebooklm-mcp__note` 讀取策略摘要 note，取得「最後更新」日期
3. 比對：source title 中的日期（格式如 `2026-01-23-共學-早上.m4a`）是否有 > 最後更新日期的
   - **沒有新 source** → 告知用戶「沒有新會議紀錄，策略不需更新」→ 結束
   - **有新 source** → 繼續 Step 2

### Step 2: 萃取策略變化

用 `mcp__notebooklm-mcp__notebook_query` 查詢：

```
notebook_id: a83bf056-1fdb-46e8-897f-4d5abd0ea704
query: "針對以下持倉標的與觀察名單，比對最新的會議內容與目前的投資策略摘要，列出有哪些變化。變化包括：thesis 調整、新增/移除關注重點、風險評估變化、持倉調整（買進/賣出/加減碼）、新增/移除觀察標的。只列出跟個股投資相關的內容，忽略行政事務。
持倉：LEU, TSM, MU, NVDA, GOOGL, AMZN, ORCL
觀察：OKLO, UUUU, GLW, AMD, AVGO, QCOM, RXRX, SNDK"
```

### Step 3: 判斷是否需要更新

讀取現有策略摘要 note 的內容，與 Step 2 的結果比對：

- **有實質變化**（thesis 改變、新增/移除標的、關注重點調整）→ 繼續 Step 4
- **無實質變化**（只是重複既有內容）→ 只更新「最後更新」日期 → 結束

### Step 4: 更新策略摘要 Note

用 `mcp__notebooklm-mcp__note` 的 `update` action：

```
notebook_id: a83bf056-1fdb-46e8-897f-4d5abd0ea704
action: update
note_id: 47d23812-c892-4133-8f6b-61a4238df00b
content: <更新後的完整策略摘要>
```

**更新規則：**
- 保留所有現有標的的策略（即使這次會議沒提到）
- 只修改有變化的部分
- 新增的標的加到對應位置（In Pool 或 Observe）
- 被移除的標的標記為「已出場」並保留歷史記錄
- 底部更新「最後更新: YYYY-MM-DD」

**策略摘要的深度要求：**
每個標的應包含：
- **核心敘事**：買入的根本原因，不是一句話而是有邏輯鏈的描述
- **關注重點（看多/看空）**：分正面與負面因素，標明時間軸
- **新聞篩選指引**：✅ 要抓的、❌ 不要的、⚠️ 需謹慎的
- 參考 LEU 的寫法作為範本

### Step 5: 完成報告

輸出：
```
✅ 策略更新完成（2026-03-XX）
   新 source 數量：X 份（從 YYYY-MM-DD 到 YYYY-MM-DD）
   變化摘要：
   - LEU: 更新了 ACP 建廠時程（延至 2031）
   - TSM: 新增 CoWoS 產能關注點
   - RXRX: 從觀察名單移除
```

## 注意事項

- **不要自己編造策略** — 所有內容必須來自會議錄音（NotebookLM query 結果）
- **保守更新** — 會議中只是隨口提到的不算策略變化，要有明確的討論和結論
- **用戶確認** — 更新前先列出變化摘要讓用戶確認，確認後再寫入 note
- **「待補充」的標的** — 如果會議中首次深入討論某個之前「待補充」的標的，就補上完整策略
