# CLAUDE.md

## 個股研究規則

### 財務數據精準度
- 財報數字必須 **100% 精準**，不能瞎掰、不能隨便從網路找到就貼上
- 財務數據（現金、營收、EPS 等）必須從本地資料庫拉取：
  - GAAP 三表：`public/data/financials/{TICKER}/{TICKER}_financials.json`
  - 補充數據（Non-GAAP、Segment）：`{TICKER}_supplemental.json`
- **取最新一期**，不要假設哪一期是最新的，讀檔確認
- 引用時標明數據來源期別（如「Q2 FY2026, SEC filing」）
- 需要核實數字時，用 NotebookLM query 核對

### 個股資訊查找
- 所有跟個股相關的訊息，**優先到 NotebookLM（work profile）查找**
- 回覆時必須隨附訊息來源（source）
- 來源引用格式：
  - **優先**：可構造的 URL（如 SEC filing），提供 `#:~:text=` highlight 連結
  - **備選**：文件名 + 高辨識度搜尋關鍵字（≤10 中文字 或 ≤5 英文單字）
- Supplemental 數據（segment revenue、Non-GAAP EPS）一律用 NotebookLM query，不用 XBRL Instance 解析
- Perplexity API 非必要不用，token 很貴

### Research Log
- 每次修改個股研究**內容**後，主動更新 Obsidian Research Log
- 路徑：`Obsidian vault/Khouse/Semiconductors/{TICKER}/Research_Log.md`
- 記錄：基本面變動、財務數據更新、新消息、投資判斷調整
- 不記錄：前端功能開發、UI 調整、bug fix

## 新聞 Pipeline 規則

- 投資策略中寫「待補充」的標的，**不得自行判斷篩選條件**，應寬鬆納入
- 只有策略中有明確篩選指引的標的，才按策略條件篩選

## NotebookLM 安全規則

- NotebookLM 無 undo、無版本控制，**寫壞就沒了**
- 任何寫入操作前：
  1. 用 ToolSearch 拉回最新 schema
  2. 確認 action 存在、參數定義符合預期
  3. 確認不會意外覆蓋資料
- 不要假設 schema 跟上次一樣，每次重新確認

## 代碼規則

- 不寫 hack，考慮全局影響和後續擴展
- 大改動前先 commit/push 或用 worktree，確保原本的東西不會被改壞
- 表格要簡潔，每欄一個重點，不塞長段文字

## 工具偏好

- Python 套件用 `uv run --with <package> python3 -c "..."` 執行，不用 `pip3` 安裝
