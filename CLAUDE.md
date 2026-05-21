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

Updated: 2026-05-21T10:48:34.049488

Project scope: `ai_agent`

## Global Working Memory
# [Working] Shared AI Working Memory (global)

Updated: 2026-05-21T10:48:33.899822

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
### export-ticker-ppt 優化方向：主筆記 IS+假設情境 dual-table slide 對應規格（2026-05-19 AAOI 實證）
# export-ticker-ppt 優化方向：主筆記 IS+假設情境 dual-table slide 對應規格（2026-05-19 AAOI 實證）
# export-ticker-ppt skill 優化方向：主筆記 → 估值推估細節 slide 的對應規格
Date: 2026-05-19
Project scope: obsidian / AAOI valuation
Status: 已用手動方式驗證 pattern 成功（共學_季報_AAOI.pptx 新增 v20260519-1 / v20260519-2 兩張 slide）

### Financials Viewer v2 — 3 frontend bugs fixed (column alignment / long-tail double display / Q4 union) 2026-05-17
# Financials Viewer v2 — 3 frontend bugs fixed (column alignment / long-tail double display / Q4 union) 2026-05-17
# Financials Viewer v2 — 3 frontend bugs fixed
Date: 2026-05-17
Project: ai_agent
Status: 已 ship 到 working tree（未 commit），dev server 驗證通過、無 console error

### Phase 6 清理：72 小時冷卻後刪除舊 iCloud Vault & ~/Documents/AI_Memory_Local
# Phase 6：舊 iCloud Vault & Milvus 資料目錄清理 Checklist
**最早執行日**：2026-05-19（搬遷後 72 小時冷卻期結束）
**Context**：2026-05-15 把 Obsidian vault 從 iCloud 搬到 `~/Obsidian/`、Milvus 資料從 `~/Documents/AI_Memory_Local/` 搬到 `~/AI_Memory_Local/`。冷卻期是為了確認所有 hardcoded path 都改對、沒有漏網之魚。三天無問題後即可清掉舊副本。
## 步驟 1 — 健康確認（執行前必跑）
確認以下全部 ✅ 才可進入步驟 2：

### migration watch test
# Migration Watch Test
Direct host write to test the inotify-based watch pipeline on the new vault path.
Sentinel: **MIGRATION-WATCH-TEST-CALIPER-2026**

### Khouse 財務圖表工作流：Tracker .qmd 作為 source of truth，主筆記 .qmd 直接共用 chunk
# Khouse 財務圖表工作流：Tracker .qmd 作為 source of truth，主筆記 .qmd 直接共用 chunk
# Khouse 財務圖表工作流：Tracker .qmd 作為 source of truth，主筆記 .qmd 直接共用 chunk
Date: 2026-05-14
Project scope: obsidian / Khouse research
Context: AAOI Financials.md tracker 開發過程確立的 pattern

### Phase 3 separated schema tmp prototype 完工 — XBRL Calc Linkbase 跨 3 ticker 0 ❌（INTC/AAOI/SNDK）2026-05-14
# Phase 3 separated schema tmp prototype 完工 — XBRL Calc Linkbase 跨 3 ticker 0 ❌（INTC/AAOI/SNDK）2026-05-14
# Phase 3 separated schema tmp prototype 完工
Date: 2026-05-14
Project: ai_agent
Status: **完整 tmp 實作完成，未 deploy 到 production**。等 user 跑更多 ticker / 更多期測試後再決定要不要合進 CC_Switch_Config。

### SEC 4 個 parse skill 的 schema 路線圖：三表/Non-GAAP inline → 未來升級 separated (Phase 3, before compose/derive)
# SEC 4 個 parse skill 的 schema 路線圖：三表/Non-GAAP inline → 未來升級 separated (Phase 3, before compose/derive)
# SEC 4 個 parse skill 的 schema 路線圖
Date: 2026-05-13
Project: ai_agent
Status: parse-SEC-supplement 已 separated 上線；三表 GAAP + 8-K Non-GAAP 暫保 inline，未來 Phase 3 升級

### wiki-ingest-sec-10k redesign pending: split OCR'd MD prose from XBRL JSON numbers (2026-05-13)
# wiki-ingest-sec-10k redesign pending: split OCR'd MD prose from XBRL JSON numbers (2026-05-13)
# wiki-ingest-sec-10k redesign pending: split OCR'd MD prose from XBRL JSON numbers
Date: 2026-05-13
Project scope: ai_knowledge_system
Status: **設計討論完成、改 skill 工作交給下個 session**。下個 session 直接看這份就能接手，不必重推。

## Project Working Memory
# [Working] Shared AI Working Memory (project:ai_agent)

Updated: 2026-05-21T10:48:33.916210

This file is the short-term shared handoff context for Claude Code, Codex, and Gemini.
Use it for current state. Use `search_memory` for older or more detailed history.

## Project Scope
- project: `ai_agent`

## Status Authority
- Latest project status authority: `docs/STATUS.md` at the project repo root.
- Before deep code inspection, read `docs/STATUS.md` first when it exists.
- After meaningful project changes, assess whether `docs/STATUS.md` should be updated.

## Recent Project Memory
### AI Memory Daily Log: 2026-05-21 (ai_agent)
# AI Memory Daily Log: 2026-05-21 (ai_agent)
## 10:48:33 [claude] "TICKER_CIK 應該從 {ticker}_gaap.json 的 metadata.cik 動態讀" 你自己直接改。
### Intent (raw)
"TICKER_CIK 應該從 {ticker}_gaap.json 的 metadata.cik 動態讀" 你自己直接改。
另外一件事，怎麼讓前端的顯示小數位跟.PDF上面的一樣？ 或是乾脆所有科目都小數後一位，EPS單獨小數後2位

### AI Memory Daily Log: 2026-05-20 (ai_agent)
# AI Memory Daily Log: 2026-05-20 (ai_agent)
## 23:52:12 [claude] 兩個都要根治，所以如果都走路徑一，就都根治對吧？那就根治它吧。
### Intent (raw)
兩個都要根治，所以如果都走路徑一，就都根治對吧？那就根治它吧。
### Summary (Haiku)

### AI Memory Daily Log: 2026-05-19 (ai_agent)
# AI Memory Daily Log: 2026-05-19 (ai_agent)
## 23:39:37 [claude] 還有需要繼續交互測試下去嗎？還是可以直接重跑所有的 ticker，去看看到底完不完整？
### Intent (raw)
還有需要繼續交互測試下去嗎？還是可以直接重跑所有的 ticker，去看看到底完不完整？
因為你跟 GPT 一直在交互，其實我已經沒在盯著細節了，所以現在不知道細節進行到什麼程度。

### AI Memory Daily Log: 2026-05-18 (ai_agent)
# AI Memory Daily Log: 2026-05-18 (ai_agent)
## 23:10:13 [claude] 請寫一個關於開發現況與測試狀況的 Markdown。
### Intent (raw)
請寫一個關於開發現況與測試狀況的 Markdown。
看是要跟輸出的內容放在一起，還是放在其他地方？我看 TMP 資料夾裡面有個 derived_base，看是不是放那裡比較好。

### AI Memory Daily Log: 2026-05-17 (ai_agent)
# AI Memory Daily Log: 2026-05-17 (ai_agent)
## 23:46:34 [claude] 好
### Intent (raw)
好
### Summary (Haiku)

### AI Memory Daily Log: 2026-05-16 (ai_agent)
# AI Memory Daily Log: 2026-05-16 (ai_agent)
## 23:53:18 [claude] 1. sec_financial_*
### Intent (raw)
1. sec_financial_*
2./financials

### AI Memory Daily Log: 2026-05-15 (ai_agent)
# AI Memory Daily Log: 2026-05-15 (ai_agent)
## 01:21:45 [claude] '/Users/mensch5566/AI_Agent/tmp/financials-viewer-redesign-plan.md'
### Intent (raw)
'/Users/mensch5566/AI_Agent/tmp/financials-viewer-redesign-plan.md'
• 已補上去，追加在 tmp/financials-viewer-redesign-plan.md:2525 的 §19. GPT-5.5 Review of Plan v5 — 開工前 v5.1 小

### AI Memory Daily Log: 2026-05-14 (ai_agent)
# AI Memory Daily Log: 2026-05-14 (ai_agent)
## 17:15:53 [claude] 直接動工改 v3 寫回 tmp/financials-viewer-redesign-plan.md
### Intent (raw)
直接動工改 v3 寫回 tmp/financials-viewer-redesign-plan.md
### Outcome (raw)
<!-- AI_MEMORY_MANAGED_END -->
