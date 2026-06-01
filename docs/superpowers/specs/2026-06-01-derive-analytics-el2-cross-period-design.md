# derive-analytics Phase D — EL2 跨期引擎（ROE/ROA 起手）Design Spec / Codex Review

Date: 2026-06-01 / Project: ai_agent
Status: 設計待 Codex review。storage contract 已拍板（`ttm_duration`）。第一階段範圍：**ROE + ROA（annual + quarterly-TTM）**。
背景：`docs/derive-analytics-expansion-plan.md` §6/§7、本 session 已上線的 EL0/EL1（11 rules）。

> 給 GPT/Codex review **設計**（尚未寫 code）。請挑戰口徑、period 拓撲正確性、storage/前端 contract、與既有引擎邊界。
> **保持質疑**：以下是我的判斷，請挑戰；同意才實作。

---

## 0. EL2 是什麼 / 為什麼

EL0/EL1 的指標都在「單一期間」自給自足（margin、流動比、D/E、FCF…）。EL2 是**跨多期**才算得出的三類：
- **報酬率**：ROE（TTM淨利 ÷ 平均權益）、ROA（TTM淨利 ÷ 平均總資產）、ROIC…
- **效率/周轉**：asset/inventory turnover、DSO/DIO/DPO、CCC…
- **成長率**：營收/EPS YoY…

三個「跨期積木」：①**TTM 加總**（最近 4 單季相加）②**期初期末平均餘額**③**去年同期 lookup（YoY）**。

## 1. 第一階段範圍（YAGNI）

**只做 ROE + ROA**（annual + quarterly-TTM 兩種）。理由：最高分析價值（巴菲特核心），且剛好把最難的積木①+②都用到——引擎立起來後 turnover/DSO/CCC 是同積木便宜加，YoY（積木③）當獨立小單元跟著做。

**排除**：Net-Debt/EBITDA（要 EBITDA，被 stale-parse 擋著，見 STATUS）；ROIC（需 NOPAT + invested capital，口徑較重）；turnover/DSO/CCC/YoY（follow-on）。

**不受 stale-parse 影響**：ROE/ROA 用 IS 單季 net_income（Q1/Q2/Q3 已有 + Q4 = derive-base `derived_q4`）+ BS instant equity/assets。CF 的 YTD/單季 stale 問題與此**無關**，可在現行 production 資料上算。

## 2. 口徑（plan §7 要求動工前定義）

| 項 | 定義 |
|---|---|
| **ROE** | TTM淨利 ÷ 平均股東權益（annual 版 = FY淨利 ÷ 平均權益）|
| **ROA** | TTM淨利 ÷ 平均總資產（annual 版同理）|
| **TTM淨利** | 最近 4 個**單季** `net_income` 相加（Q1/Q2/Q3 = `quarter_duration`；Q4 = `derived_q4`）。湊不滿 4 季 → skip |
| **平均餘額** | **2 點平均** (期初 + 期末) ÷ 2 |
| **平均餘額 period（quarterly-TTM）** | 期初 = **去年同季**期末餘額、期末 = 本季期末。例 TTM-ending-Q3_FY2025：avg = (equity@Q3_FY2024 + equity@Q3_FY2025)/2 |
| **平均餘額 period（annual）** | 期初 = 上一 FY 期末、期末 = 本 FY 期末。例 FY2025：avg = (equity@FY2024 + equity@FY2025)/2 |
| **權益 / 資產** | `total_equity` / `total_assets`（BS, instant）|
| **N/M / skip** | 平均分母 ≤ 0 → skip（負權益 ROE 無意義）；TTM 湊不滿 4 季 → skip；缺去年同季/上年底餘額 → skip（最早期數自然無前值）|
| **unit / 顯示** | `Pure`，pct-style（顯示 %、可為負，**非** RATIO_AS_MULTIPLE）|
| **version** | GAAP（NON_GAAP 無 BS/CF facts，自動 skip）|

**待 Codex 拍板的口徑**：
- 平均餘額用 **2 點**（begin+end）/2 vs **5 點**（TTM 視窗 5 個季末平均）。我選 2 點（教科書常見、資料需求最少）。
- `total_equity` 是否該排除少數股權/特別股（common equity）。我選先用 total_equity，未來再細修。

## 3. storage contract（已拍板）

| 視圖 | period_kind | period label |
|---|---|---|
| quarterly ROE/ROA（TTM）| **`ttm_duration`**（新增）| `Qx_FYyyyy` = TTM 結束季 |
| annual ROE/ROA | `fy_annual_duration` | `FYyyyy` |

- **新增 period_kind `ttm_duration`**：語意乾淨（period_kind 本就是期間語意欄）。`provenance.window='TTM'` 也帶上（雙保險）。
- DB：production metrics 的 period_kind 看來無硬 check constraint（5 個現值自由文字）；上線前確認 upsert 不擋新值。
- **不可**把 TTM 偽裝成 `quarter_duration`（plan §6 明令）。

## 4. 跨期引擎設計（新模組）

新檔 `rules_crossperiod.py`（與 EL1 `rules_ratios.py` 分開——EL1 是單期、EL2 是跨期，邊界清楚），`compute_crossperiod_metrics(facts) -> [RatioCandidate]`。

### 4.1 period 拓撲 helper（`period_topology.py`）
- `parse_period("Q3_FY2025") -> (2025, 3)`；`("FY2025") -> annual`。
- `trailing_quarters((Y,q), n=4) -> [(Y',q')...]`：q 遞減，<1 時 FY-1、q 回 4。例 (2025,3) → [(2024,4),(2025,1),(2025,2),(2025,3)]。
- `year_ago_quarter((2025,3)) -> (2024,3)`（avg-balance 期初 + 未來 YoY）。
- `prior_fy(2025) -> 2024`（annual avg-balance 期初）。

### 4.2 compute
1. index facts by `(period, version, statement, uni_account)`（含 derive-base `derived_q4` net_income）。
2. 對每個 target period（每個有 net_income 的季 / FY）×（ROE, ROA）：
   - **TTM淨利**：trailing 4 季 net_income 全在 → sum；缺一季 → skip。
   - **平均餘額**：lookup 期初/期末 BS（equity 或 assets）instant；缺一邊 → skip；avg ≤ 0 → skip。
   - value = TTM淨利 / 平均餘額；annual 版用 FY淨利 / 平均(上年底,今年底)。
   - period_kind：quarterly → `ttm_duration`；annual → `fy_annual_duration`。
   - `provenance.formula`（如 `"net_income_TTM(Q4_FY2024+Q1+Q2+Q3_FY2025) / avg(total_equity@Q3_FY2024, @Q3_FY2025)"`）+ `inputs`（4 季 NI + 2 餘額，各帶 cell_id/unit）+ `window`。
3. 輸出 RatioCandidate（statement='RATIO', unit='Pure'）。

### 4.3 與 EL1 的邊界
EL1（rules_ratios）不動。EL2 是平行新模組；`derive_analytics.py` 跑完 EL1 後再跑 EL2，合併 rows 寫同一份 `analytics_metrics`。`ALL_RULE_IDS` 併入 EL2 rule_ids（`RATIO_ROE` / `RATIO_ROA`）。

## 5. 前端
- `RATIO_ROWS += roe, roa`（pct-style，net_margin 附近）。
- `useFinancialMatrix`：**新增 `ttm_duration` 路由** —— quarterly RATIO 視圖除了 `quarter_duration ∪ derived_q4`，ROE/ROA 這類要撈 `ttm_duration`；annual 撈 `fy_annual_duration`。比照現有「BS-derived ratio 用 instant」的 statement-aware 分流，新增「TTM-derived ratio 用 ttm_duration」。
- tooltip：標 `TTM (trailing 12M)` + formula。
- chart：pct group（同 margin）。

## 6. 測試（TDD）
- `period_topology`：trailing-4 跨年 wrap、year-ago、prior-fy。
- TTM 加總（含 derived_q4）、缺季 skip。
- 平均餘額（2 點、缺邊 skip、≤0 skip）。
- ROE/ROA 數值（annual + quarterly-TTM）、period_kind 正確、formula/inputs。
- 既有 EL0/EL1 11 rules regression 不變。
- 前端 `tsc` + `ttm_duration` 路由（preview 驗 quarterly view 出 ROE TTM、annual 出 FY ROE）。

## 7. 部署 / 驗證
- 5-mirror sync；四 ticker 重跑 + `--apply`。
- 抽期對帳：ROE = TTM淨利 / 平均權益，手算一兩期對 production facts。
- 不變式：合理區間（科技股 ROE 多在 5%~40%；負淨利期可為負）。

## 8. 待 Codex 挑戰
1. 平均餘額 2 點 vs 5 點？`total_equity` vs common equity？
2. period 拓撲：TTM-ending-Q 的平均餘額期初取「去年同季」對嗎（vs 視窗起點 = trailing-4 的第一季「之前」一季期末）？我認為兩者同指——去年同季期末 = 4 季前期末 = 視窗起點前一期。請驗。
3. `ttm_duration` 新 period_kind 是否衝擊其他既有 consumer（adapter 校驗、derive-base、Obsidian JSON、valuation tab）？
4. annual ROE 的「平均(上年底,今年底)」——最早 FY 無前值 skip，可接受嗎？

## 9. 之後（不在本階段）
turnover/DSO/DIO/DPO/CCC（同積木①②）、YoY（積木③）、Net-Debt/EBITDA（待 EBITDA / stale-parse）、ROIC。
