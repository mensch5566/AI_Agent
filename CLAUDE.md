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
- project_root: `/Users/mensch5566/AI_Agent/.claude/worktrees/statement-view-pdf-faithful`
- project_scope: `statement-view-pdf-faithful`

## Status Discipline
- Latest project status authority: `docs/STATUS.md` at the project repo root.
- Before deep code inspection, read `docs/STATUS.md` first when it exists.
- After meaningful project changes, assess whether `docs/STATUS.md` should be updated.

Treat the following Working Memory as the current project context. Use `search_memory` when you need older or more detailed history.

# [Working] Combined AI Working Memory

Updated: 2026-06-09T16:18:20.181010

Project scope: `statement-view-pdf-faithful`

## Global Working Memory
# [Working] Shared AI Working Memory (global)

Updated: 2026-06-09T16:18:19.864425

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
### CF cash movement-analysis COMPLETE + verified (prod + browser, both modes)
# CF cash movement-analysis COMPLETE + verified (prod + browser, both modes)
# CF cash 期初/期末 movement-analysis — 完成且端到端驗證
Date: 2026-06-09 / worktree `statement-view-pdf-faithful`（未 merge main / 未 push）
## ✅ 全部完成 + 驗證
EFM §7.7 movement analysis：底層一個 instant（period-end balance），顯示層讓同值=本期期末=下期期初；單季期初=上季末，絕不相減。

### CF cash MA — Task1 (adapter relabel) DONE; Task2/3 frontend + re-upsert pending
# CF cash MA — Task1 (adapter relabel) DONE; Task2/3 frontend + re-upsert pending
# CF cash movement-analysis — 實作進度（Task1 完成）
Date: 2026-06-08 / worktree `statement-view-pdf-faithful` (未 merge main/未 push)
Spec（design-converged, Codex×4）: docs/superpowers/specs/2026-06-08-cf-cash-movement-analysis-design.md
## ✅ Task 1 DONE + verified (commit 6cbb1e5)

### CF cash begin/end — movement-analysis design CONVERGED (impl pending)
# CF cash begin/end — movement-analysis design CONVERGED (impl pending)
# CF cash 期初/期末 — movement-analysis 設計收斂，待實作
Date: 2026-06-08 / Project: ai_agent (worktree `statement-view-pdf-faithful`) / Tier: T2
## 背景 bug（已驗證）
前端 CF「現金期末餘額」被標成「at beginning of period」：季模式 `ending_cash`(Q2_FY2026=13934)、年模式 `cf_long_tail`(FY2025=9646) 都中。根因：resolver 把 cash concept 盲挑 `matched[0]`=periodStart arc。且真正的「期初」行缺失。YTD facts(6M/9M) 前端 statement view 排除、不顯示。

### TradingView Pine PE 腳本驗證：邏輯正確=GAAP，前述「TradingView 矛盾」誤判已更正
# TradingView Pine PE 腳本驗證：邏輯正確=GAAP，前述「TradingView 矛盾」誤判已更正
# TradingView Pine PE 腳本驗證結論（更正先前誤判）
Date: 2026-06-09 / Project: obsidian / 適用：Khouse/Macro_Weekly 雙周報 slide 22（NASDAQ Top 10 History P/E Ratio）的 PE 數據可信度確認。
## 背景
雙周報 slide 22 的各標的 current + 1Y/2Y/3Y/5Y 平均 PE，來源是使用者在 TradingView 上跑的 Pine 腳本（`/Users/mensch5566/Downloads/Pine.txt`，手抄進 slide）。使用者要確認這支腳本跑出來的數字「有沒有問題」。**不是要做自動化**（使用者明確說現在沒有要自動化）。

### 估值 memo 參數百分比格式：寫成 N%（如 4%、35.5%），非小數也非整數裸值
# 估值 memo 參數百分比格式：寫成 N%（如 4%、35.5%），非小數也非整數裸值
# 估值 memo 參數百分比格式：`N%`
Date: 2026-06-04 / Project: obsidian / 適用：所有 `03_Working/Valuation/v20xx-xx-xx*.md` 估值版本筆記的參數表（MU、LITE、AAOI…）。Claude/Codex/Gemini 共用。
（取代 2026-06-04 早先「小數兩位」那條 memory——當時會錯意，已刪。）
## 規則（user 2026-06-04 明確指定）

### 估值模型填歷史數字：GAAP Total OpEx 必須 = GP−OI，勿加總元件（parse-10QK-gaap long_tail 符號 bug）
# 估值模型填歷史數字：GAAP Total OpEx 必須 = GP−OI，勿加總元件（parse-10QK-gaap long_tail 符號 bug）
# 估值模型填歷史數字的紀律 + parse-10QK-gaap GAAP OpEx 元件相加 bug
Date: 2026-06-04 / Project: obsidian / 適用：所有從 parse json 填 `*_Financial_Model.xlsx` 歷史實績的估值模型（MU、LITE、AAOI…）。Claude/Codex/Gemini 共用。
## 核心紀律（已更正：正確來源是 derive-base，不是 raw parse）
填歷史實績時，**錨定 reported 小計、各值有直接 json 來源就直接拿**：

### BS long-tail Phase 0 完成（cal period fiscal+axis fix，MU 驗證過），Phase 1 待接 2026-06-03
# BS long-tail Phase 0 完成（cal period fiscal+axis fix，MU 驗證過），Phase 1 待接 2026-06-03
# BS long-tail Phase 0 — 完成、已驗證、已同步；Phase 1 待接（含前端 merge point）
Date: 2026-06-03 / Project: ai_agent / Skill: parse-10QK-gaap / Tier: T3
spec：`docs/superpowers/specs/2026-06-02-parse-bs-long-tail-design.md`（v3）；ADR：`docs/adr/ADR-002-bs-long-tail-catch-all.md`。AI_Agent branch：**`bs-long-tail-design`**（docs commit aeae383）。
## Phase 0 做了什麼（cal linkbase period 標籤 fiscal+axis-aware）

### BS long-tail Design-gate 產出完成（spec v2 + ADR-002 + Project Profile），待 Codex round-2 2026-06-03
# BS long-tail Design-gate 產出完成（spec v2 + ADR-002 + Project Profile），待 Codex round-2 2026-06-03
# BS long-tail catch-all — Design-gate 產出完成，待 Codex round-2 + 人類核可
Date: 2026-06-03 / Project: ai_agent / Skill: parse-10QK-gaap / Tier: T3
依新版 Software Development SOP（`~/Obsidian/SOPs/Development/Software Development SOP.md`）走 T3 生命週期，目前在 **Design gate**。
## 已產出（branch `bs-long-tail-design`，commit 2269709，3 檔）

## Project Working Memory
# [Working] Shared AI Working Memory (project:statement-view-pdf-faithful)

Updated: 2026-06-09T16:18:20.044654

This file is the short-term shared handoff context for Claude Code, Codex, and Gemini.
Use it for current state. Use `search_memory` for older or more detailed history.

## Project Scope
- project: `statement-view-pdf-faithful`

## Status Authority
- Latest project status authority: `docs/STATUS.md` at the project repo root.
- Before deep code inspection, read `docs/STATUS.md` first when it exists.
- After meaningful project changes, assess whether `docs/STATUS.md` should be updated.

## Recent Project Memory
### AI Memory Daily Log: 2026-06-09 (statement-view-pdf-faithful)
# AI Memory Daily Log: 2026-06-09 (statement-view-pdf-faithful)
## 16:18:19 [claude] 依財報和標準科目寫成英文。
### Intent (raw)
依財報和標準科目寫成英文。
然後你這兩版都驗收通過了嗎？

### AI Memory Daily Log: 2026-06-08 (statement-view-pdf-faithful)
# AI Memory Daily Log: 2026-06-08 (statement-view-pdf-faithful)
## 17:27:43 [claude] 我記得EBITDA和FCF都是派生值，PDF上面是不會在三表裡的，如果我沒說錯的話，
### Intent (raw)
我記得EBITDA和FCF都是派生值，PDF上面是不會在三表裡的，如果我沒說錯的話，
那就 suppress（兩模式一致，EBITDA/FCF 只在 Ratios 分頁）

### AI Memory Daily Log: 2026-06-06 (statement-view-pdf-faithful)
# AI Memory Daily Log: 2026-06-06 (statement-view-pdf-faithful)
## 01:22:43 [claude] 你自己檢查過了嗎？
### Intent (raw)
你自己檢查過了嗎？
### Summary (Haiku)

### AI Memory Daily Log: 2026-06-05 (statement-view-pdf-faithful)
# AI Memory Daily Log: 2026-06-05 (statement-view-pdf-faithful)
## 23:17:00 [claude] 繼續吧
### Intent (raw)
繼續吧
### Summary (Haiku)

### AI Memory Daily Log: 2026-06-04 (statement-view-pdf-faithful)
# AI Memory Daily Log: 2026-06-04 (statement-view-pdf-faithful)
## 23:31:26 [claude] A
### Intent (raw)
A
### Outcome (raw)
<!-- AI_MEMORY_MANAGED_END -->
