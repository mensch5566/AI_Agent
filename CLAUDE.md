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
- **isEps() 判斷**：台股 key 是 `eps_basic`/`eps_diluted`，不是 `basic_eps`/`diluted_eps`
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

Updated: 2026-07-02T23:33:39.560705

Project scope: `ai_agent`

## Global Working Memory
# [Working] Shared AI Working Memory (global)

Updated: 2026-07-02T23:33:38.995077

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
### 財報 skill 命名重構 + derive 走A + compose 加台股(2026-07-02 拍板待執行)
# 財報 skill 命名重構 + derive 走A + compose 加台股(2026-07-02 拍板待執行)
# 財報 skill 命名重構 + derive 市場無關化 + compose 台股(2026-07-02 使用者拍板,待新 session 執行)
## 1. 改名(美股+台股)— `parse-{市場}-*` 抽取層;共用層不帶市場 token
- `parse-10QK-gaap`→`parse-us-gaap`
- `parse-8k-nongaap`→`parse-us-nongaap`

### 台股/美股財報最終輸出必須指標邏輯一致（鐵律）
# 台股/美股財報最終輸出必須指標邏輯一致（鐵律）
# 台股/美股財報最終輸出必須指標邏輯一致（鐵律，2026-06-26 使用者強調）
台股（TWSE iXBRL）與美股（SEC XBRL API）的**最終輸出必須指標邏輯一致**：不論資料怎麼清洗、解析、來源如何不同（SEC companyfacts API vs TWSE iXBRL HTML vs NLM PDF 讀取），**最後出來的三表科目結構（`uni_account` 命名）與 derive 指標（derive-base identities + derive-analytics ratios / QoQ / YoY）都要跟美股一樣**。管道差異只能存在於抽取層，一律收斂到同一套 canonical schema。
## Why
前端 Financial Viewer、derive-base、derive-analytics 是台美共用層。台股若自創 uni_account 命名或 derive 口徑，就無法跟美股同框顯示、同套 ratio 計算，破壞跨市場可比性與單一 SSOT 紀律。

### AI_Token_Counter Plan 8 全部上線：discover-other + 個人CSV log + merge-csv + 每人資料夾/Total聚合，pushed origin 819f390，148 test
# AI_Token_Counter Plan 8 全部上線：discover-other + 個人CSV log + merge-csv + 每人資料夾/Total聚合，pushed origin 819f390，148 test
# AI_Token_Counter Plan 8 全部完工並 push 上 GitHub（2026-06-29）
承接同日「Plan 8 merged 未 push」那筆。**全部做完、merge 進 main、push 上 origin。148 test 綠。正式環境就緒，組員可 pull。**
## GitHub
- origin/main @ `819f390`（push 完成，`77d81b2..819f390`）。repo `mensch5566/AI_Token_Counter`。

### AI_Token_Counter Plan 8 完工 merged：--discover-other + 個人CSV純log + merge-csv，145 test，main 242595e 未push
# AI_Token_Counter Plan 8 完工 merged：--discover-other + 個人CSV純log + merge-csv，145 test，main 242595e 未push
# AI_Token_Counter Plan 8 完工（2026-06-29）— merged 進 main，未 push
承接「Plan 7 快速穩定 haiku」。User 痛點：宣告 --project 後不符合的全擠進一個大 Other（6/22-26 真跑 Other 63%），看不出在做什麼；且多人週報要能聚合。**Plan 8 全做完、TDD、code review 過、merge 進 main、145 test 綠。**
## 兩個功能（都 merged）
### 1. `tokencount cluster --discover-other`（搭 --project）

### AI_Token_Counter Plan 8 進行中：--discover-other（宣告任務+Haiku 命名剩餘），TDD，138 test，branch feat/discover-other-tasks 未 merge
# AI_Token_Counter Plan 8 進行中：--discover-other（宣告任務+Haiku 命名剩餘），TDD，138 test，branch feat/discover-other-tasks 未 merge
# AI_Token_Counter Plan 8（--discover-other：宣告任務 + Haiku 自動命名剩餘）進行中（2026-06-29）
承接「Plan 7 快速穩定 haiku 完工」。User 痛點：宣告 --project 後，不符合的全擠進一個大 Other（6/22-26 真跑 Other 佔 63%），看不出在做什麼。要「比照宣告的三個 task 的顆粒度，讓 Haiku 找出類似的新任務」。
## 使用者宣告的三個 task（6/22-26 週報）
981A（統一00981A PCF 儀表板）、Stock Weekly（個股週報）、康寧（Corning 個股研究）。來自 6/22-23 Plan 7 實跑記錄。

### AI_Token_Counter Plan 7 完工：haiku 分類快速+不卡，根因是「分類全 corpus」非 claude -p 慢，6/22-23 實跑驗證過
# AI_Token_Counter Plan 7 完工：haiku 分類快速+不卡，根因是「分類全 corpus」非 claude -p 慢，6/22-23 實跑驗證過
# AI_Token_Counter Plan 7（快速+穩定 haiku 分類）完工（2026-06-28）
承接「Plan 6 宣告式分類完工」+ user 模擬正式週報時 haiku **跑一小時卡死**。**Plan 7 修好,已 merge+push。131 test。6/22-23 真實 haiku 實跑 96 秒跑通、Gate C tol=0、0 timeout、項目歸對。**
## GitHub
main @ `a67343e`,merge commit。plan=`docs/superpowers/plans/2026-06-28-plan7-fast-robust-haiku.md`。

### AI_Token_Counter Plan 6 完工：宣告式項目分類 + agent guide，--project + Haiku 分類，125 test
# AI_Token_Counter Plan 6 完工：宣告式項目分類 + agent guide，--project + Haiku 分類，125 test
# AI_Token_Counter Plan 6（宣告式項目分類 + agent guide）完工（2026-06-28）
承接「Plan 5 filters+CSV 完工」。**Plan 6 加上「宣告式項目分類」+ Claude Code 使用說明書 + CSV 編碼修正，已 merge+push。125 test。真資料 Haiku 分類 demo 過。**
## GitHub
main @ `7b8a619`，merge commit。spec=`docs/superpowers/specs/2026-06-28-plan6-declared-project-classification-design.md`，plan=`docs/superpowers/plans/2026-06-28-plan6-declared-project-classification.md`。

### AI_Token_Counter Plan 5 完工：日期/來源篩選 + CSV 匯出,真資料 Haiku CSV demo 過,113 test
# AI_Token_Counter Plan 5 完工：日期/來源篩選 + CSV 匯出,真資料 Haiku CSV demo 過,113 test
# AI_Token_Counter Plan 5（filters + CSV）完工（2026-06-28）
承接「Plan 4 CLI 完工」。**Plan 5 加上日期/來源篩選 + CSV 匯出,已 merge+push。113 test。真資料 Haiku CSV demo 跑過,使用者看到按 date×task 的 token 分佈。**
## GitHub
main @ `806e831`,merge commit `806e831`。plan: `docs/superpowers/plans/2026-06-28-plan5-filters-csv.md`。

## Project Working Memory
# [Working] Shared AI Working Memory (project:ai_agent)

Updated: 2026-07-02T23:33:39.046014

This file is the short-term shared handoff context for Claude Code, Codex, and Gemini.
Use it for current state. Use `search_memory` for older or more detailed history.

## Project Scope
- project: `ai_agent`

## Status Authority
- Latest project status authority: `docs/STATUS.md` at the project repo root.
- Before deep code inspection, read `docs/STATUS.md` first when it exists.
- After meaningful project changes, assess whether `docs/STATUS.md` should be updated.

## Recent Project Memory
### AI Memory Daily Log: 2026-07-02 (ai_agent)
# AI Memory Daily Log: 2026-07-02 (ai_agent)
## 23:33:38 [claude] <task-notification>
### Intent (raw)
<task-notification>
<task-id>a5657768a3fac2c02</task-id>

### AI Memory Daily Log: 2026-07-01 (ai_agent)
# AI Memory Daily Log: 2026-07-01 (ai_agent)
## 08:24:31 [claude] <scheduled-task name="financials-synthetic-check" file="/Users/mensch5566/.claud
### Intent (raw)
<scheduled-task name="financials-synthetic-check" file="/Users/mensch5566/.claude/scheduled-tasks/financials-synthetic-check/SKILL.md">
This is an automated run of a scheduled task. The user is not present to answer questions. For implementation details, execute autonomously without asking clarifying questions — make reasonable choices and note them in your output. "write" actions (e.g. MCP tools that send, post, create, update, or delete), only take them if the task file asks for that specific action. When in doubt, producing a report of what you found is the correct output.

### AI Memory Daily Log: 2026-06-30 (ai_agent)
# AI Memory Daily Log: 2026-06-30 (ai_agent)
## 08:39:24 [claude] <scheduled-task name="financials-synthetic-check" file="/Users/mensch5566/.claud
### Intent (raw)
<scheduled-task name="financials-synthetic-check" file="/Users/mensch5566/.claude/scheduled-tasks/financials-synthetic-check/SKILL.md">
This is an automated run of a scheduled task. The user is not present to answer questions. For implementation details, execute autonomously without asking clarifying questions — make reasonable choices and note them in your output. "write" actions (e.g. MCP tools that send, post, create, update, or delete), only take them if the task file asks for that specific action. When in doubt, producing a report of what you found is the correct output.

### AI Memory Daily Log: 2026-06-29 (ai_agent)
# AI Memory Daily Log: 2026-06-29 (ai_agent)
## 08:43:07 [claude] <scheduled-task name="financials-synthetic-check" file="/Users/mensch5566/.claud
### Intent (raw)
<scheduled-task name="financials-synthetic-check" file="/Users/mensch5566/.claude/scheduled-tasks/financials-synthetic-check/SKILL.md">
This is an automated run of a scheduled task. The user is not present to answer questions. For implementation details, execute autonomously without asking clarifying questions — make reasonable choices and note them in your output. "write" actions (e.g. MCP tools that send, post, create, update, or delete), only take them if the task file asks for that specific action. When in doubt, producing a report of what you found is the correct output.

### AI Memory Daily Log: 2026-06-28 (ai_agent)
# AI Memory Daily Log: 2026-06-28 (ai_agent)
## 08:29:56 [claude] <scheduled-task name="financials-synthetic-check" file="/Users/mensch5566/.claud
### Intent (raw)
<scheduled-task name="financials-synthetic-check" file="/Users/mensch5566/.claude/scheduled-tasks/financials-synthetic-check/SKILL.md">
This is an automated run of a scheduled task. The user is not present to answer questions. For implementation details, execute autonomously without asking clarifying questions — make reasonable choices and note them in your output. "write" actions (e.g. MCP tools that send, post, create, update, or delete), only take them if the task file asks for that specific action. When in doubt, producing a report of what you found is the correct output.

### AI Memory Daily Log: 2026-06-27 (ai_agent)
# AI Memory Daily Log: 2026-06-27 (ai_agent)
## 08:29:44 [claude] <scheduled-task name="financials-synthetic-check" file="/Users/mensch5566/.claud
### Intent (raw)
<scheduled-task name="financials-synthetic-check" file="/Users/mensch5566/.claude/scheduled-tasks/financials-synthetic-check/SKILL.md">
This is an automated run of a scheduled task. The user is not present to answer questions. For implementation details, execute autonomously without asking clarifying questions — make reasonable choices and note them in your output. "write" actions (e.g. MCP tools that send, post, create, update, or delete), only take them if the task file asks for that specific action. When in doubt, producing a report of what you found is the correct output.

### AI Memory Daily Log: 2026-06-26 (ai_agent)
# AI Memory Daily Log: 2026-06-26 (ai_agent)
## 17:20:35 [claude] 好
### Intent (raw)
好
### Summary (Haiku)

### AI Memory Daily Log: 2026-06-25 (ai_agent)
# AI Memory Daily Log: 2026-06-25 (ai_agent)
## 17:08:58 [claude] 你看一下LITE的FY26Q3的Non-GAAP EPS 在前端怎麼是2？ 是小數位被砍掉了嗎
### Intent (raw)
你看一下LITE的FY26Q3的Non-GAAP EPS 在前端怎麼是2？ 是小數位被砍掉了嗎
### Summary (Haiku)
<!-- AI_MEMORY_MANAGED_END -->
