# CLAUDE.md

## 個股研究規則

### 財務數據精準度與統一管道
- 財報數字必須 **100% 精準**，不能瞎掰、不能隨便從網路找到就貼上
- **所有財務數據必須透過統一管道寫入 Supabase**，禁止直接 INSERT/UPDATE

#### 台股 XBRL 管道 (Taiwan TWSE)
路徑：`/Tools/research-tools/parse-twse-ixbrl/`
1. 本地讀取 TWSE 手動下載的 XBRL HTML 檔案
2. `batch_parse.py` → 批量解析並提取指標
3. 與 NotebookLM 驗證（讀取對應 ticker 筆記本，比對差異）
4. 人工複審差異項（異常標註、補充說明）
5. 確認無誤後寫入 `financial_facts` + `financial_companies`
6. 補足 XML 上無直接提供的指標（從 NotebookLM 或補充表）
7. source tag：`XBRL_TWSE`

#### 美股 SEC 管道 (US Securities)
路徑：`/Tools/research-tools/parse-sec-filing/`
1. 從 SEC Edgar XBRL API 下載 10-Q/10-K
2. `parse_sec.py` → 解析並提取 GAAP 指標
3. NotebookLM 補足 Segments、Non-GAAP 等指標
4. 確認無誤後寫入 `financial_facts` + `financial_companies`
5. source tag：`XBRL_SEC`

#### Financial Guidance 管道（後續）
路徑：`/Tools/research-tools/parse-guidance/`
- 從 Earnings Call / Press Release 提取 guidance 數據
- 寫入 **獨立表** `financial_guidance`（不污染 GAAP 原始數據）
- source tag：`GUIDANCE_{COMPANY}` 或 `GUIDANCE_ANALYST`

#### Derived Metrics（派生指標）
- ROE、ROA、current_ratio 等**計算指標**不寫進 `financial_facts`
- 寫入**獨立表** `financial_metrics`（同時記錄計算公式）
- 目的：隔離官方 XBRL 數據 vs. 衍生計算

#### 數據修正流程
- 發現 XBRL 數據有誤 → 重新下載官方版本 + 重新解析
- 以官方修正版為準，覆蓋舊數據
- 不保留舊版本（除非官方同時發佈更正聲明）

- **取最新一期**，不要假設哪一期是最新的，查 Supabase 確認
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

## Financial Viewer 開發規則

**任何涉及財務報表（Financial Viewer）的開發，開始前必須走以下流程：**

### 開工前三步（強制）

1. **讀 skill 文件**
   - `Tools/research-tools/parse-twse-ixbrl/skill.md`
   - 必看：Known Limitations、CHANGELOG（裡面記錄了踩過的坑）

2. **讀表結構清單**
   - `docs/financials-view-schema.md`
   - 確認要動的指標在哪張表、是否已確認、有無待處理項目
   - **未確認的指標不得寫入、計算或前端讀取**

3. **確認 DB 現況**
   - 查 Supabase 確認實際數據，不要靠記憶假設
   - 特別確認：financial_metrics 的 pct 指標是小數格式（0.4814）不是百分比（48.14）

### 開工後（修完要做）

- 跑 skill.md 裡的驗證腳本確認數值正確
- 把本次修的 bug/改動補進 skill.md 的 CHANGELOG
- 有新的 Known Limitation 也補進去

### 關鍵陷阱備忘

- **Supabase 預設 1000 row limit**：超過 20 期 × 87 項就會截斷，API 必須用 range() pagination
- **Q4 EPS 是全年值**：XBRL 無 Q4 單季 EPS，`basic_eps`/`diluted_eps` 在 Q4 存全年
- **financial_metrics 格式**：存小數（0.4814），前端 fmtVal 會乘 100，不要改成百分比
- **isEps() 判斷**：台股 key 是 `basic_eps`/`diluted_eps`，不是 `eps_basic`/`eps_diluted`
- **toAnnual() metric 名稱**：台股用 `operating_revenue`，美股舊格式用 `revenue`

## 代碼規則

- 不寫 hack，考慮全局影響和後續擴展
- 大改動前先 commit/push 或用 worktree，確保原本的東西不會被改壞
- 表格要簡潔，每欄一個重點，不塞長段文字

## 工具偏好

- Python 套件用 `uv run --with <package> python3 -c "..."` 執行，不用 `pip3` 安裝
