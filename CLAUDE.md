# CLAUDE.md

## Status Discipline

- `docs/STATUS.md` 是這個 repo 的正式狀態來源
- 開始深入看 code 之前，先讀 `docs/STATUS.md`
- 有實質功能、資料源、workflow 變更後，要評估是否更新 `docs/STATUS.md`
- AI Memory 的 working memory 應只做 handoff 與提醒，不取代 repo 內正式文件
- `CLAUDE.md` 與 `AGENTS.md` 在這個 repo 應視為同級的 agent 規則入口，內容應盡量保持一致
- 如果 `AGENTS.md`、`CLAUDE.md`、working memory 有重疊規則，以 repo 內正式文件與最新 `docs/STATUS.md` 為準

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
   - `docs/financials-architecture.md` ← v0.4 架構（dual-key + long-tail bucket + Non-GAAP reconciliation metadata + SEC 合規）
   - `docs/financials-core-checklist.md` ← v4 核心 metric 清單
   - `docs/financials-view-schema.md`
   - `docs/financials-data-rules.md`
   - 確認要動的指標在哪張表、是否已確認、有無待處理項目
   - **每筆 cell 的 schema 紀律**：
     - `uni_account` 必須屬於：(1) 核心 universal key（在 schema 已確認），或 (2) 12 個 long-tail bucket（`{section}_long_tail`）+ `misc_long_tail` catch-all
     - 每筆 cell 必須有 `weight`（XBRL calculation weight，+1/-1）
     - Long-tail cell 額外帶 `long_tail_metadata`（is_recurring / last_occurrence_date / rolls_up_to）
   - **不允許自由創造新的 uni_account 名稱**（未認得的科目 → LLM 判定 section → 配對應 bucket）
   - 升級 long-tail item 為核心：在 schema 文件登記 + 打勾「確認」 + 加 IS_TAG_MAP 候選 + 重抽歷史

3. **確認 DB 現況**
   - 查 Supabase 確認實際數據，不要靠記憶假設
   - 特別確認：financial_metrics 的 pct 指標是小數格式（0.4814）不是百分比（48.14）

### 開工後（修完要做）

- 跑 skill.md 裡的驗證腳本確認數值正確
- 把本次修的 bug/改動補進 skill.md 的 CHANGELOG
- 有新的 Known Limitation 也補進去

### 關鍵陷阱備忘

- **Supabase 預設 1000 row limit**：超過 20 期 × 87 項就會截斷，API 必須用 range() pagination
- **台股 Q4 EPS 要重建單季值**：XBRL 年報常只給全年 EPS，quarterly view 要用 `FY - Q1 - Q2 - Q3` 還原 `Q4` 單季 EPS，不能直接用全年值
- **Quarterly 不得顯示 annual-only 值**：若台股 `Q4` 單季值無法可靠重建，quarterly view 寧可留空，也不能直接顯示全年值
- **financial_metrics 格式**：存小數（0.4814），前端 fmtVal 會乘 100，不要改成百分比
- **isEps() 判斷**：台股 key 是 `basic_eps`/`diluted_eps`，不是 `eps_basic`/`eps_diluted`
- **toAnnual() metric 名稱**：台股用 `operating_revenue`，美股舊格式用 `revenue`
- **每筆 cell 必須帶 unit 欄位**：不同公司會用不同 reporting scale（INTC=`USD_millions`、AAOI=`USD_thousands`），display layer 直接讀 row 的 `unit` 欄位決定顯示，不要 hardcode 預設 millions
- **美股 USD scale auto-detect**：`parse-10QK-gaap` 用 max revenue 量級判斷（>=$1B → `USD_millions`，否則 `USD_thousands`）。小公司硬轉 millions 會顯示成 0.05 / 53.030 失去直觀，跟 PDF 對不上
- **SG&A 子科目合併處理**：當公司只報 `SellingAndMarketingExpense` + `GeneralAndAdministrativeExpense`（缺合併 tag），pipeline 自動 sum 補核心 SG&A，**同時**把兩個子值寫進 `operating_expense_long_tail` bucket（`rolls_up_to=selling_general_administrative`），子科目訊息不能丟
- **NLM ↔ SEC unit 對照**：cross_check 用 SEC 端的 unit 決定是否要 rescale NLM 值。同 scale 直接 1:1 對應，跨 scale（罕見）才換算。tolerance 在不同 scale 下意義不同（thousands 下 0.001 = $1，millions 下 0.001 = $1000）

## 代碼規則

- 不寫 hack，考慮全局影響和後續擴展
- 大改動前先 commit/push 或用 worktree，確保原本的東西不會被改壞
- 表格要簡潔，每欄一個重點，不塞長段文字

## 工具偏好

- Python 套件用 `uv run --with <package> python3 -c "..."` 執行，不用 `pip3` 安裝<!-- AI_MEMORY_MANAGED_START -->
# Shared AI Memory Context

This section is auto-generated by AI Memory. Edit outside this managed block.
- project_root: `/Users/mensch5566/AI_Agent`
- project_scope: `ai_agent`

## Status Discipline
- Latest project status authority: `docs/STATUS.md` at the project repo root.
- Before deep code inspection, read `docs/STATUS.md` first when it exists.
- After meaningful project changes, assess whether `docs/STATUS.md` should be updated.
- Current working tree has non-trivial changes without a `docs/STATUS.md` edit; review whether the status doc needs an update before finishing.

Treat the following Working Memory as the current project context. Use `search_memory` when you need older or more detailed history.

# [Working] Combined AI Working Memory

Updated: 2026-06-23T12:23:43.069021

Project scope: `ai_agent`

## Global Working Memory
# [Working] Shared AI Working Memory (global)

Updated: 2026-06-23T12:23:42.594937

This file is the short-term shared handoff context for Claude Code, Codex, and Gemini.
Use it for current state. Use `search_memory` for older or more detailed history.

## System Anchors
# [System] Memsearch 專案部署與 Patch 指南
## 專案目標
建立可持久化、跨 session、跨模型共用的本地語義記憶庫，將模型本身與記憶層解耦。
## 目錄與路徑設計
- Git 專案根目錄：`/Users/mensch5566/AI_Memory`
- Obsidian 記憶來源：`/Users/mensch5566/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian/AI_Memory_Inbox`
- Milvus/etcd/minio 本機資料：`/Users/mensch5566/Documents/AI_Memory_Local/milvus`
- ONNX/HuggingFace 快取：`/Users/mensch5566/Documents/AI_Memory_Local/memsearch-cache`
## docker-compose 關鍵設定
- `etcd`、`minio`、`milvus` 提供 self-hosted Milvus standalone 底座
- `memsearch-worker` 掛載 Obsidian Inbox 到容器內 `/memory`
- `memsearch-worker` 使用 `python /workspace/scripts/run_memsearch_cli.py watch /memory` 常駐監看
- Milvus 連線使用容器內網位址：`http://milvus:19530`
## 重要設定檔
- `docker-compose.yml`：定義四個服務與 volume bind mounts
- `.memsearch.toml`：固定 embedding provider = `onnx`，milvus uri = `http://milvus:19530`
- `.mcp.json`：提供 Claude Code 的 project-scoped MCP 設定
## Python Wrapper 的作用

## Recent Shared Memory
### Fund_Research 00981A PCF：step 4 離線 dashboard 完成 + git/GitHub 上線
# Fund_Research 00981A PCF：step 4 離線 dashboard 完成 + git/GitHub 上線
# Fund_Research 00981A PCF：step 4 離線 dashboard 完成（2026-06-23）
承接 step 4 交接那筆。**前端 dashboard 做完、測試綠、git init + push 到 private GitHub。** 整個 00981A PCF 專案（step 1-4）至此完成。
## 產出（repo `/Users/mensch5566/Fund_Research`，已 push）
- **GitHub**：https://github.com/mensch5566/Fund_Research（**private**，branch master）。

### Fund_Research 00981A PCF：step 4 前端 dashboard 開發交接（資料層已完成）
# Fund_Research 00981A PCF：step 4 前端 dashboard 開發交接（資料層已完成）
# Fund_Research 00981A PCF：step 4 前端 dashboard 開發交接（2026-06-23）
要轉隔壁 session 繼續**前端**（step 4：離線 HTML viewer）。資料層（step 1-3）已完成且 bulletproof，下面是接手 step 4 需要的一切。
## 現況：資料層完成
- 抓取程式 `scripts/fetch_pcf.py`（Python3+requests）+ skill `.claude/skills/update-pcf/SKILL.md`。

### Fund_Research 00981A PCF：GPT-5.5 review 後強化抓取程式（TWSE 日曆驗證層 + 8 項修正）
# Fund_Research 00981A PCF：GPT-5.5 review 後強化抓取程式（TWSE 日曆驗證層 + 8 項修正）
# Fund_Research 00981A PCF：GPT-5.5 review 後強化（2026-06-23）
承接 step 3。user 要求讓 GPT-5.5（codex exec, xhigh）adversarial review 抓取邏輯，目標「絕不能出錯：有交易的日子不能漏、沒交易的日子不能撈」。已採納全部建議並實作完。
## 採納 GPT 8 項 + 額外，全部已實作（scripts/fetch_pcf.py）
1. **靜默漏資料/連帶錯位（CRITICAL）**：交易日抓取若重試用盡仍偏移/payload 殘缺/網路失敗 → 記為 failure，**寫檔前若有任何 failure 就中止、不寫、exit 非 0**（FetchError）。不再 return None 靜默跳過。

### Fund_Research 00981A PCF：step 3 全歷史回補完成 + update-pcf skill；發現並修掉 TranDate 偏移坑
# Fund_Research 00981A PCF：step 3 全歷史回補完成 + update-pcf skill；發現並修掉 TranDate 偏移坑
# Fund_Research 00981A PCF：step 3 完成（全歷史回補 + skill）（2026-06-22）
承接 step 2 那筆。**step 3 全歷史回補完成、寫成 skill**。下一步只剩 step 4（離線 HTML viewer + 三組分析）。
## 產出
- **skill（project-scoped）**：`.claude/skills/update-pcf/SKILL.md`。觸發語：「更新 00981A」「抓最新 PCF」「回補 PCF 歷史」等。

### Fund_Research 00981A PCF：抓取程式 step 2 完成（fetch_pcf.py 跑通）
# Fund_Research 00981A PCF：抓取程式 step 2 完成（fetch_pcf.py 跑通）
# Fund_Research 00981A PCF：抓取程式 step 2 完成（2026-06-22）
承接「00981A PCF 本地離線 HTML dashboard 開發交接」那筆的「下一步」第 2 點。**抓取程式已寫好並實測跑通**。
## 產出
- `scripts/fetch_pcf.py`（Python3 + requests）。CLI：

### Fund_Research 專案：00981A PCF 本地離線 HTML dashboard — 開發交接
# Fund_Research 專案：00981A PCF 本地離線 HTML dashboard — 開發交接
# Fund_Research 專案：00981A PCF 本地離線 HTML dashboard（開發交接，2026-06-22）
承接 Obsidian session。使用者要轉到隔壁 session 接續開發。以下是完整交接，**架構決策已鎖定，下一步是寫抓取程式**。
## 專案目標
把 00981A（統一台股增長主動式 ETF，統一投信）每週 PCN 分析做成**本地離線 HTML dashboard**。**呈現型、不做線上部署**、雙擊 HTML 離線可看。

### GLW production re-upsert 完成 + 4 個 upsert-gate 修正(canonical fallback/period_end/8k coerce/audit-meta preserve)
# GLW production re-upsert 完成 + 4 個 upsert-gate 修正(canonical fallback/period_end/8k coerce/audit-meta preserve)
# GLW production re-upsert SHIPPED (2026-06-18)
承接 GLW 四鏈完成那筆。user 授權 production re-upsert,**已寫入 Supabase**(純 insert、0 deleted、GLW 全新 ticker)。
## production 寫入結果
sec_financial_companies 1 / sec_financial_facts 3,083 / sec_financial_dimensional_facts 178 / sec_financial_edges 4,441 / sec_financial_metrics 496(derive-base)+526(analytics)。全部 0 deleted。

### GLW onboard 1-2-3-4 全部完成(parse/8k/supplement/derive);待 production re-upsert
# GLW onboard 1-2-3-4 全部完成(parse/8k/supplement/derive);待 production re-upsert
# GLW (Corning) onboard — 四兄弟 + derive 全鏈完成 (2026-06-18)
承接前一筆 GLW memory(① 完成那筆)。user「1,2,3,4 依序跑」**全部跑完**。所有輸出在本機 JSON,**production Supabase 待 re-upsert(需授權)**。GLW 是**全新 ticker**(production 尚無 GLW)。
## 四鏈最終狀態(本機 Skill_Output)
- **① parse-10QK-gaap**:IS 889 / BS 652 / CF 700 rows(含 **63 個 IS audit cell**:R&D 面額 29 + extension long-tail 34)。cal sum sanity 0 ❌。

## Project Working Memory
# [Working] Shared AI Working Memory (project:ai_agent)

Updated: 2026-06-23T12:23:42.637355

This file is the short-term shared handoff context for Claude Code, Codex, and Gemini.
Use it for current state. Use `search_memory` for older or more detailed history.

## Project Scope
- project: `ai_agent`

## Status Authority
- Latest project status authority: `docs/STATUS.md` at the project repo root.
- Before deep code inspection, read `docs/STATUS.md` first when it exists.
- After meaningful project changes, assess whether `docs/STATUS.md` should be updated.

## Recent Project Memory
### AI Memory Daily Log: 2026-06-23 (ai_agent)
# AI Memory Daily Log: 2026-06-23 (ai_agent)
## 12:23:42 [claude] Subagent-Driven
### Intent (raw)
Subagent-Driven
### Outcome (raw)

### AI Memory Daily Log: 2026-06-22 (ai_agent)
# AI Memory Daily Log: 2026-06-22 (ai_agent)
## 17:42:30 [claude] 聯亞沒有合併報表，因為它沒有子公司，所以它的個體報表就是總表。
### Intent (raw)
聯亞沒有合併報表，因為它沒有子公司，所以它的個體報表就是總表。
iXBRL裡面難道還有分合併和個體？

### AI Memory Daily Log: 2026-06-21 (ai_agent)
# AI Memory Daily Log: 2026-06-21 (ai_agent)
## 08:29:46 [claude] <scheduled-task name="financials-synthetic-check" file="/Users/mensch5566/.claud
### Intent (raw)
<scheduled-task name="financials-synthetic-check" file="/Users/mensch5566/.claude/scheduled-tasks/financials-synthetic-check/SKILL.md">
This is an automated run of a scheduled task. The user is not present to answer questions. For implementation details, execute autonomously without asking clarifying questions — make reasonable choices and note them in your output. "write" actions (e.g. MCP tools that send, post, create, update, or delete), only take them if the task file asks for that specific action. When in doubt, producing a report of what you found is the correct output.

### AI Memory Daily Log: 2026-06-20 (ai_agent)
# AI Memory Daily Log: 2026-06-20 (ai_agent)
## 08:29:34 [claude] <scheduled-task name="financials-synthetic-check" file="/Users/mensch5566/.claud
### Intent (raw)
<scheduled-task name="financials-synthetic-check" file="/Users/mensch5566/.claude/scheduled-tasks/financials-synthetic-check/SKILL.md">
This is an automated run of a scheduled task. The user is not present to answer questions. For implementation details, execute autonomously without asking clarifying questions — make reasonable choices and note them in your output. "write" actions (e.g. MCP tools that send, post, create, update, or delete), only take them if the task file asks for that specific action. When in doubt, producing a report of what you found is the correct output.

### AI Memory Daily Log: 2026-06-19 (ai_agent)
# AI Memory Daily Log: 2026-06-19 (ai_agent)
## 08:30:07 [claude] <scheduled-task name="financials-synthetic-check" file="/Users/mensch5566/.claud
### Intent (raw)
<scheduled-task name="financials-synthetic-check" file="/Users/mensch5566/.claude/scheduled-tasks/financials-synthetic-check/SKILL.md">
This is an automated run of a scheduled task. The user is not present to answer questions. For implementation details, execute autonomously without asking clarifying questions — make reasonable choices and note them in your output. "write" actions (e.g. MCP tools that send, post, create, update, or delete), only take them if the task file asks for that specific action. When in doubt, producing a report of what you found is the correct output.

### AI Memory Daily Log: 2026-06-18 (ai_agent)
# AI Memory Daily Log: 2026-06-18 (ai_agent)
## 14:55:19 [claude] In the GLW (Corning) SEC GAAP facts source JSON, 5 `is_long_tail` IS rows are ma
### Intent (raw)
In the GLW (Corning) SEC GAAP facts source JSON, 5 `is_long_tail` IS rows are manual audit-cells for glw: extension below-line items but have `long_tail_metadata: null` (no `rolls_up_to`). Because of this they cannot receive a canonical-order display ordinal and GLW's IS coverage gate stays at 99.2% (5 rows missing ordinal) in `python3 scripts/upsert_sec_financials.py GLW`.
The 5 rows are:

### AI Memory Daily Log: 2026-06-17 (ai_agent)
# AI Memory Daily Log: 2026-06-17 (ai_agent)
## 13:20:08 [claude] 寫
### Intent (raw)
寫
### Summary (Haiku)

### AI Memory Daily Log: 2026-06-16 (ai_agent)
# AI Memory Daily Log: 2026-06-16 (ai_agent)
## 23:56:15 [claude] 你可以 search memory 一下，我們稍早有找出來，它沒有放在 .env 裡面。
### Intent (raw)
你可以 search memory 一下，我們稍早有找出來，它沒有放在 .env 裡面。
之前 AI agent 已經有放過那個 FRED 的 API key 了，但不是放在 .env，而是放在其他地方。你找一下，你自己放進去就行了
<!-- AI_MEMORY_MANAGED_END -->
