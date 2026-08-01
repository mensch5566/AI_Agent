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
路徑：`parse-twse-ixbrl` skill（`~/.claude/skills/parse-twse-ixbrl/`，`run.sh`→`parse_ixbrl.py`；canonical=`~/CC_Switch_Config/skills/parse-twse-ixbrl/`）。
（舊 `Tools/research-tools/parse-twse-ixbrl/batch_parse.py` 已 DEPRECATED，勿用。）
1. `run.sh fetch <ticker> <西元年> <季>` 從 MOPS 官方 API 下載 iXBRL 原始檔並落地（archive-first）
2. `run.sh parse <ticker>` → 解析三表為 `{T}_twse_facts.json`（純抽值，絕不運算）
3. `parse-tw-crosscheck` skill 與 NotebookLM 逐期 tol=0 交叉驗證（讀對應 ticker 筆記本，比對差異）
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

Treat the following Working Memory as the current project context. Use `search_memory` when you need older or more detailed history.

# [Working] Combined AI Working Memory

Updated: 2026-07-11T22:16:20.779011

Project scope: `ai_agent`

## Global Working Memory
# [Working] Shared AI Working Memory (global)

Updated: 2026-07-11T22:16:20.019565

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
### 台燿 6274 全29期MOPS財報已進正式Wiki(FY19Q1→FY26Q1);renderer直上production驗證;台股wiki-ingest全流程完工
# 台燿 6274 全29期MOPS財報已進正式Wiki(FY19Q1→FY26Q1);renderer直上production驗證;台股wiki-ingest全流程完工
# 台燿 (6274) 全 29 期 MOPS 進正式 Wiki 完工(2026-07-11)
承接「mops-10k deterministic renderer 建成上線」。台股 wiki-ingest 全流程走完:skill 上線 → renderer 上線 → 11 期近期 promote → 18 期歷史直上 production。
## 最終狀態
- **正式 `Obsidian/Wiki` 有台燿全 29 期**(FY19Q1→FY26Q1,本地財報全覆蓋):29 source 頁 + entity `台燿.md`(29 期 Operating Arc)+ 2 comparison(6274-fy26q1-vs-fy25q1、6274-fy25q4-vs-fy24q4)。index.md(29 catalog + entity line + 2 Current-State bullet,rev 6)+ log.md(promote + backfill 兩筆)。

### mops-10k deterministic renderer 建成+上線(render_source_page + update_page);11期台燿reconcile;wiki-ingest補Step0;正式頁待promote
# mops-10k deterministic renderer 建成+上線(render_source_page + update_page);11期台燿reconcile;wiki-ingest補Step0;正式頁待promote
# mops-10k renderer 建成上線 + wiki update 能力(2026-07-11)
承接「wiki-ingest-mops-10k 4-layer JSON 升級完工(2026-07-10)」。這輪:回補 5 期→10 期、隔壁 derive-analytics 擴充變動率、建 deterministic renderer、reconcile 10 期、e2e 驗、發佈上線、補 wiki-ingest Step 0。
## 為什麼建 renderer
之前所有踩到的錯(Block E 標籤、Elite Material 幻覺)全是 **LLM 逐頁手排 A–F** 犯的;bundle 數字本身零錯。→ 把 A–F + frontmatter provenance 做成**確定性 renderer**,LLM 只寫 Block G 敘述 + entity 合成。這也補上專案缺的「wiki update 能力」(re-render = update)。

### wiki-ingest-mops-10k 4-layer JSON 升級完工上線(子專案B);台燿5期staging已審未promote;24期回補+production待辦
# wiki-ingest-mops-10k 4-layer JSON 升級完工上線(子專案B);台燿5期staging已審未promote;24期回補+production待辦
# wiki-ingest-mops-10k 4-layer JSON 升級(子專案 B)完工上線(2026-07-10)
承接 parse-tw-supplement(子專案 A,2026-07-08 完工)。台股 wiki ingest 從舊 OCR/iXBRL-HTML 架構**原地升級**成讀 4 層 JSON、as-reported vs derived 分區塊、絕不自算——對齊美股 wiki-ingest-sec-10k v3。
## 交付(全部完成)
- **Skill 上線**:`~/CC_Switch_Config/skills/wiki-ingest-mops-10k/`(master `e92759c`,path-scoped 不碰隔壁 session 的 pine-pe/md-to-ppt)。**3 鏡像 byte-identical**(SSOT=~/.claude/skills=~/.cc-switch/skills),已 sync-to-local。**未 push origin**(要 push 再說)。

### parse-tw-supplement 全部完工並上線:台燿 6274 29 期 supplement(部門/地區/客戶)已產出+驗證+合併push;子專案B可接手
# parse-tw-supplement 全部完工並上線:台燿 6274 29 期 supplement(部門/地區/客戶)已產出+驗證+合併push;子專案B可接手
# parse-tw-supplement 全部完工並上線(2026-07-08)—— 子專案 A 收尾
承接「parse-tw-supplement spec v1.1 argue 收斂 → 交隔壁 session 開發」。**建構 + 台燿 29 期 live 回補 + 合併 push 全部完成**。
## 交付
- **Skill 建構(TDD,subagent-driven)**:`~/CC_Switch_Config/skills/parse-tw-supplement/`(canonical SSOT)= `tw_supplement_core.py`(純核心:ROC→CE 含「X年度」年報式 + period_kind/period_end + axis-by-section + alias + process_fact/merge_key + edges/merge)、`extract_tw_supplement.py`、`cross_check_tw_supplement.py`、`ticker_configs/6274.json`、`SKILL.md`。43 test 綠。

### 台燿 6274 部門附註有揭「部門資產/負債」(business_segment identifiable_assets)——刻意不納入通用 supplement 開發
# 台燿 6274 部門附註有揭「部門資產/負債」(business_segment identifiable_assets)——刻意不納入通用 supplement 開發
# 台燿 6274 部門「資產負債表」刻意略過通用開發(2026-07-08 使用者拍板)
## 事實(留存,不開發)
台燿 (6274) 的合併財報**部門資訊附註**(節號跨期漂移:三四/三五/三六)底下,除了 (一)部門收入與營運結果,多數期別還有 **(二)部門總資產與負債**——即 **business_segment 維度的部門資產 + 部門負債**。例:Q4 FY2025(114/12/31,instant)國內銷售及製造部門資產 17,578,620 / 國外 16,545,078 / 未分攤之資產 5,617,392 / 部門資產總額 39,741,090。**Q3 沒揭**(季報非強制,揭露跨期不對稱)。
## 使用者決定

### ROE 杜邦拆解段：一次性腳本待評估產品化（compose 加 roe-dupont section？）；聯亞被 prune 事故已復原
# ROE 杜邦拆解段：一次性腳本待評估產品化（compose 加 roe-dupont section？）；聯亞被 prune 事故已復原
# ROE 杜邦拆解段——腳本產品化評估（移交隔壁，2026-07-08）
## 現狀
台燿 6274 與聯亞 3081 的 `Financials.md` 現在都有「## ROE 拆解（DuPont）」手寫段：**放在 AUTO 區塊外**（compose 重跑不會洗掉、但也不會自動更新），格式 = 公式註 + 雙軸圖（`{ticker}_roe-dupont.png`：淨利率左軸%、資產周轉/槓桿右軸倍）+ 12 季表（ROE/ROA/淨利率/資產周轉/槓桿）+ 判讀 + 注意。GLW 也有同款（更早的手寫版）。
## 事故教訓（已修復）

### compose-financials 台股 Q4 單季完工（feat/compose-tw-q4，鏡像已上線）；CC_Switch_Config 分支糾纏待隔壁 supplement session 解
# compose-financials 台股 Q4 單季完工（feat/compose-tw-q4，鏡像已上線）；CC_Switch_Config 分支糾纏待隔壁 supplement session 解
# compose-financials 台股 Q4 單季完工（2026-07-08）— 分支問題移交隔壁 session
## 完成了什麼（全部驗證過，READY）
`compose-financials --market tw` 現在會渲染 **Q4 單季欄**：IS/CF 讀 derive-base `derived_q4` rows、BS 用 as-reported 年末值、ratio 由 analytics Q4 rows 自動填。台燿 6274 實跑驗證：Q4 FY25 revenue = 9,124,783、capex 翻回負號（-457,017）、Q4 EPS `—`、IS section 尾註「Q4 EPS 不還原…」恰一次、Q1-Q3 既有值 byte-identical。美股 GLW 重跑 **完全零 diff**。52 test 綠。**三份鏡像（CC_Switch_Config canonical / ~/.claude/skills / ~/.cc-switch/skills）已 rsync 同步 = 功能已實際上線可用**，剩下的只是 git 歷史整潔問題。
## 關鍵實作（4 commits on feat/compose-tw-q4 @ CC_Switch_Config）

### parse-tw-supplement spec v1.1 argue 收斂完成,交隔壁 session 開發;wiki-ingest-mops-10k 升級(子專案B)留 AI_Knowledge_System
# parse-tw-supplement spec v1.1 argue 收斂完成,交隔壁 session 開發;wiki-ingest-mops-10k 升級(子專案B)留 AI_Knowledge_System
# parse-tw-supplement spec v1.1 收斂完成 → 交接開發(2026-07-07)
## 大局
「台燿 (6274) 進 Wiki」計畫拆兩個子專案:
- **子專案 A = parse-tw-supplement**(台股三表以外維度揭露 parse skill,本 memory 交接的部分)→ **交給隔壁 session 開發**。

## Project Working Memory
# [Working] Shared AI Working Memory (project:ai_agent)

Updated: 2026-07-11T22:16:20.081148

This file is the short-term shared handoff context for Claude Code, Codex, and Gemini.
Use it for current state. Use `search_memory` for older or more detailed history.

## Project Scope
- project: `ai_agent`

## Status Authority
- Latest project status authority: `docs/STATUS.md` at the project repo root.
- Before deep code inspection, read `docs/STATUS.md` first when it exists.
- After meaningful project changes, assess whether `docs/STATUS.md` should be updated.

## Recent Project Memory
### AI Memory Daily Log: 2026-07-11 (ai_agent)
# AI Memory Daily Log: 2026-07-11 (ai_agent)
## 22:16:19 [claude] 進 writing-plans
### Intent (raw)
進 writing-plans
### Summary (Haiku)

### AI Memory Daily Log: 2026-07-10 (ai_agent)
# AI Memory Daily Log: 2026-07-10 (ai_agent)
## 23:54:16 [claude] Subagent-Driven
### Intent (raw)
Subagent-Driven
### Summary (Haiku)

### AI Memory Daily Log: 2026-07-09 (ai_agent)
# AI Memory Daily Log: 2026-07-09 (ai_agent)
## 11:02:54 [claude] 那這"台燿_FY26Q1_FullReport_6274.pdf"是哪來的？
### Intent (raw)
那這"台燿_FY26Q1_FullReport_6274.pdf"是哪來的？
### Summary (Haiku)

### AI Memory Daily Log: 2026-07-08 (ai_agent)
# AI Memory Daily Log: 2026-07-08 (ai_agent)
## 15:19:20 [claude] 補完SOP，沒問題就要交過去隔壁session做wiki ingest了
### Intent (raw)
補完SOP，沒問題就要交過去隔壁session做wiki ingest了
### Summary (Haiku)

### AI Memory Daily Log: 2026-07-07 (ai_agent)
# AI Memory Daily Log: 2026-07-07 (ai_agent)
## 23:48:07 [claude] 隔壁用 compose-financial 要輸出財務數據的時候，他說讀不到，所以他是在讀本地的 JSON。
### Intent (raw)
隔壁用 compose-financial 要輸出財務數據的時候，他說讀不到，所以他是在讀本地的 JSON。
你也順便確認一下我們 Obsidian 的 SOP 那邊，應該有說所有 Parse Skill 的使用方式吧？我記得有一個 Markdown 檔案，你去看一下上次更新是什麼時候，臺股的部分應該也需要再更新。

### AI Memory Daily Log: 2026-07-06 (ai_agent)
# AI Memory Daily Log: 2026-07-06 (ai_agent)
## 23:42:02 [claude] 我沒有要換remote，我原本只是要開claude code的/remote-control。
### Intent (raw)
我沒有要換remote，我原本只是要開claude code的/remote-control。
所以現在兩邊看保留哪個，直接push，弄上線之後我就要實際使用驗收了。

### AI Memory Daily Log: 2026-07-05 (ai_agent)
# AI Memory Daily Log: 2026-07-05 (ai_agent)
## 23:51:52 [claude] 現在背景還有一個 running task，它顯示還在等 NLM 回覆，這個是什麼回覆？
### Intent (raw)
現在背景還有一個 running task，它顯示還在等 NLM 回覆，這個是什麼回覆？
### Summary (Haiku)

### AI Memory Daily Log: 2026-07-04 (ai_agent)
# AI Memory Daily Log: 2026-07-04 (ai_agent)
## 23:55:28 [claude] <task-notification>
### Intent (raw)
<task-notification>
<task-id>a1c50bf32a54d7a68</task-id>
<!-- AI_MEMORY_MANAGED_END -->

## 本 repo 的功能文檔在 Obsidian vault

本 repo 自己的功能 → `~/Obsidian/docs/Repo/AI_Agent/<feature-name>/`

六份開發文檔（`STATUS` / `LOG` / `PITFALLS` / `ADR` / `CONTRACT` / `RULES`）一律**在 vault 更新與維護**，不放回本 repo。
開發或修改功能前先讀對應目錄；新增功能時在該處建六檔。
規則權威：`~/Obsidian/CLAUDE.md`「Feature Development Documentation（六檔）」章的**存放位置**。
