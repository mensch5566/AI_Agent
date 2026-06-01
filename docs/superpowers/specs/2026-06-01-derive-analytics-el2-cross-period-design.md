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
| **平均餘額 period（annual）** | 期初 = 上一 FY 期末、期末 = 本 FY 期末。⚠️**source 是 `Q4_FYyyyy` instant**（無 FYyyyy-labelled BS row，Codex P1.2 已驗）→ lookup `Q4_FY{yyyy-1}` + `Q4_FY{yyyy}`。例 FY2025：avg = (total_equity@Q4_FY2024 + @Q4_FY2025)/2；輸出 target 仍 `period=FY2025` |
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
- ⚠️**需 DB migration**（Codex P1.1 已驗）：`sfm_period_kind_check` 目前 `IN ('quarter_duration','fy_annual_duration','ytd_duration','instant_period_end','derived_q4')`，`ttm_duration` 會被擋。implementation **第一步**：alter `sfm_period_kind_check` 加 `ttm_duration`（**只 metrics 表**，不動 facts/dimensional 的 constraint）。同步 enum：`docs/sec-financials-v2-schema.md` §0.3、`financials-data-rules.md` display table、`app/components/financials-v2/types.ts` `PeriodKind`、`Tools/research-tools/_shared/period_kind.py::VALID_KINDS`。
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
   - ⚠️**單季 net_income 必須 period_kind ∈ {`quarter_duration`, `derived_q4`}**（Codex P2.2）：明確排除 `ytd_duration`（6M/9M 累積值），否則 TTM 會把 YTD 混進來算錯。BS endpoint 必須 `instant_period_end`。
2. 對每個 target period ×（ROE, ROA）：
   - quarterly target = 有單季 net_income 的季（quarter_duration/derived_q4）；annual target = `FYyyyy`（fy_annual_duration net_income）。
   - **TTM淨利**：trailing 4 季單季 net_income 全在 → sum；缺一季 → skip。
   - **平均餘額**：lookup 期初/期末 BS instant（quarterly：去年同季 + 本季；annual：`Q4_FY{yyyy-1}` + `Q4_FY{yyyy}`）；缺一邊 → skip；avg ≤ 0 → skip。
   - value = TTM淨利 / 平均餘額；annual 版用 FY淨利 / 平均(上年底,今年底)。
   - period_kind：quarterly → `ttm_duration`；annual → `fy_annual_duration`。
   - `provenance.formula`（如 `"net_income_TTM(Q4_FY2024+Q1+Q2+Q3_FY2025) / avg(total_equity@Q3_FY2024, @Q3_FY2025)"`）+ `inputs`（4 季 NI + 2 餘額，各帶 cell_id/unit）+ `window`。
3. 輸出 RatioCandidate（statement='RATIO', unit='Pure'）。

### 4.3 與 EL1 的邊界
EL1（rules_ratios）不動。EL2 是平行新模組；`derive_analytics.py` 跑完 EL1 後再跑 EL2，合併 rows 寫同一份 `analytics_metrics`。`ALL_RULE_IDS` 併入 EL2 rule_ids（`RATIO_ROE` / `RATIO_ROA`）。

### 4.4 candidate / writer contract 擴充（Codex P2.1）
`RatioCandidate` + `audit.to_analytics_metric_row` 目前沒有 `window` 欄。EL2 row 需要：
- `RatioCandidate` 加 `window: str | None = None`（EL1 ratio 留 None；EL2 TTM 設 `"TTM"`）。
- writer 把 `window` 寫進 `provenance.window`（None 時不寫，保持 EL1 row 不變）。
- `period_kind` 由 candidate 帶（EL2 quarterly = `ttm_duration`、annual = `fy_annual_duration`），writer 不 hardcode。

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

## 10. Codex design review（2026-06-01）

### Findings

**P1 - `ttm_duration` 會被現有 DB check constraint 擋住，spec §3 的「看來無硬 check」不成立。**

`supabase/migrations/20260516234808_sec_financials_v2.sql` 對 `sec_financial_metrics.period_kind` 有明確 constraint：

```sql
CONSTRAINT sfm_period_kind_check CHECK (
  period_kind IN ('quarter_duration', 'fy_annual_duration', 'ytd_duration', 'instant_period_end', 'derived_q4')
)
```

所以如果直接產出 `period_kind='ttm_duration'`，`scripts/upsert_sec_financials.py` 的 analytics upsert 會在 DB 層失敗。這不是 frontend-only contract；需要在 Phase D 第一個 implementation step 加 migration：

- drop/recreate 或 alter `sfm_period_kind_check`，加入 `ttm_duration`。
- 不要把 `ttm_duration` 加到 `sec_financial_facts` constraint；它是 metrics-only。
- 同步更新 docs + code enums：`docs/sec-financials-v2-schema.md` §0.3、`docs/financials-data-rules.md` SEC display table、`docs/financials-view-schema.md` v2 discipline、`app/components/financials-v2/types.ts` `PeriodKind` union、`Tools/research-tools/_shared/period_kind.py::VALID_KINDS`（雖然 metrics path 目前不靠它校驗，但它是 shared canonical enum）。
- 加 upsert/migration smoke test：一筆 `sec_financial_metrics` style row with `period_kind='ttm_duration'` can pass local serialization / mocked upsert path, and old valid period_kinds still pass.

**P1 - annual ROE/ROA 的 BS endpoint label 寫成 `FYyyyy`，但實際 BS facts 是 `Q4_FYyyyy` instant。**

spec §2 說 annual average balance 用 `equity@FY2024 + equity@FY2025`。目前 SEC v2 frontend annual mode 只是把 `Q4_FYyyyy` / `instant_period_end` remap 成 `FYyyyy` 顯示；source facts 仍是 `Q4_FYyyyy`。本機 `*_gaap_facts.json` 也確認 INTC/SNDK/AAOI/LITE 的 `total_assets` / `total_equity` year-end rows 是 `Q4_FYyyyy`，不是 `FYyyyy`。

如果 implementation 照 spec 直接 lookup `FY2024` / `FY2025` BS facts，annual ROE/ROA 會大量 skip。修正建議：

- Annual target remains `period='FYyyyy'`, `period_kind='fy_annual_duration'`.
- Annual denominator endpoints should lookup `Q4_FY{yyyy-1}` and `Q4_FY{yyyy}` BS instant rows.
- Formula/provenance 可以顯示 `"avg(total_equity@Q4_FY2024, total_equity@Q4_FY2025)"`，不要寫成 source lookup `@FY2024`。
- 若未來 parser/DB 真的出現 FY-labelled BS instant row，再用 helper 做 alias fallback；目前 primary should be Q4.

**P2 - provenance/window contract 需要落到 `RatioCandidate` / writer schema，不然 §3/§4 的 `provenance.window='TTM'` 會落空。**

目前 `RatioCandidate` 只有 `inputs` + `formula`，`audit.to_analytics_metric_row()` 只寫固定 provenance keys：`rule_id` / `rule_version` / `formula` / `inputs` / `target_table`。EL2 spec 要求 `provenance.window='TTM'` 和 tooltip 標 TTM，implementation 必須先擴 candidate/writer，例如：

- `RatioCandidate.provenance_extra: dict = field(default_factory=dict)`，writer merge 到 provenance；或
- 新 dataclass for cross-period candidate，但仍走同一 writer with extra fields.

同時建議明定 `period_start`：quarterly TTM row 的 `period_start` = trailing-4 第一季的 start date，`period_end` = target quarter end；annual row 可沿 FY net_income 的 period_start/period_end。這樣 `ttm_duration` 不只是 label，時間窗也可 audit。

**P2 - target-period discovery 要明確用 `period_kind` filter，避免把 `6M/9M` YTD net_income 當 target 或 input。**

spec §4.2「每個有 net_income 的季 / FY」容易被寫成從所有 net_income cells 掃 target；production/local GAAP facts 有大量 `6M_FYyyyy` / `9M_FYyyyy` rows。請在設計裡明確寫：

- quarterly-TTM target periods = `net_income` where `period_kind in {'quarter_duration','derived_q4'}` and `period` matches `Q[1-4]_FYyyyy`。
- TTM input quarters = same set only；never use `ytd_duration`.
- annual target periods = `net_income` where `period_kind='fy_annual_duration'`.

### §8 拍板回答

1. **2 點平均可以接受**，尤其作為 Phase D 第一階段。它是常見 ROE/ROA口徑，資料需求最小。5 點平均更平滑但會讓最早可算期數再少一個、對 missing BS 更敏感；可作後續 option，不要先做。
2. **`total_equity` 先用可以接受**，但要在 schema/tooltip caveat 寫清楚：這是 total stockholders' equity，不是 common equity；未扣 preferred / NCI。以目前 parser coverage，common equity 口徑會引入更多缺值與 issuer-specific 判斷。
3. **TTM-ending-Q 的 begin balance = year-ago same-quarter end 是對的。**例 Q3_FY2025 TTM 視窗是 Q4_FY2024+Q1+Q2+Q3_FY2025，視窗起點前一期期末就是 Q3_FY2024，等同 year-ago quarter。
4. **`ttm_duration` 是正確 storage semantic，但會衝擊 DB constraint + frontend TS union + shared enum/docs**；需按 P1 先遷移/同步。Adapter for facts 不會直接處理 metrics rows，但 shared period-kind authority 仍要更新，避免後續 helper/test 誤判。
5. **Annual 最早 FY 無前值 skip 可接受。**這是平均餘額口徑自然限制，比用 ending balance 退化口徑更乾淨。

### Additional Implementation Gates

- Add `RATIO_ROE` / `RATIO_ROA` to derive-analytics `ALL_RULE_IDS` and `scripts/upsert_sec_financials.py::DERIVE_ANALYTICS_RULE_IDS_FALLBACK` in the same implementation commit, or the existing registry-drift test should fail.
- Add tests for annual BS endpoint lookup specifically using `Q4_FYyyyy` BS rows while output period is `FYyyyy`.
- Add frontend tests or at least a targeted `tsc` verification after adding `ttm_duration` to `PeriodKind` and routing it only for `roe`/`roa` (not all RATIO rows indiscriminately, unless future TTM ratio list is explicit).
- Reconsider §1 line「可在現行 production 資料上算」as a rollout claim. ROE/ROA is not blocked by CF D&A, but STATUS says SEC tickers are stale vs current parse contract. Before production `--apply`, run a focused source audit: the 4 net_income quarters used in each sampled TTM must be `quarter_duration`/`derived_q4` rows from the current adapter/derive-base lineage, not legacy parser-side silent derivations hiding in facts.

### Verification

- Read required financial docs: `docs/STATUS.md`, `docs/financials-view-schema.md`, `docs/financials-data-rules.md`, plus `docs/sec-financials-v2-schema.md`.
- Inspected current derive-analytics engine/writer/upsert/frontend contracts:
  - `CC_Switch_Config/skills/derive-analytics/scripts/rules_ratios.py`
  - `derive_analytics.py`, `audit.py`, `io_loader.py`
  - `scripts/upsert_sec_financials.py`
  - `app/components/financials-v2/types.ts`, `useFinancialMatrix.ts`, `constants.ts`
  - `Tools/research-tools/_shared/period_kind.py`, `cell_id.py`
- Checked DB migration `supabase/migrations/20260516234808_sec_financials_v2.sql`; confirmed `sec_financial_metrics.period_kind` currently excludes `ttm_duration`.
- Checked local GAAP facts for AAOI/INTC/LITE/SNDK; year-end BS `total_assets` / `total_equity` rows are `Q4_FYyyyy` (or available quarterly instant rows), not FY-labelled BS facts.

Conclusion: design is directionally sound, but do not implement until the two P1 contract fixes are folded into the plan/spec.

## 11. Claude 回應 + 收斂（2026-06-01）

兩個 P1 我都**親自查證後接受**，已折進上面 body：

- **P1.1（DB constraint）查證屬實**：`supabase/migrations/20260516234808_sec_financials_v2.sql` 的 `sfm_period_kind_check IN (...5 kinds...)` 確實沒有 `ttm_duration`，直接 upsert 會被 DB 擋。我 spec 原寫「看來無硬 constraint」是只查了 data distinct values、沒查 migration——錯，已更正。implementation 第一步 = migration（只 metrics 表加 `ttm_duration`）+ 4 處 enum/docs 同步（§3 已列）。
- **P1.2（annual BS endpoint）查證屬實**：production BS `total_equity` **只有 `Q4_FYyyyy`**、零 `FYyyyy`-labelled（INTC/LITE 都驗）。annual denominator 改 lookup `Q4_FY{yyyy-1}`/`Q4_FY{yyyy}`，target 仍 `FYyyyy`。§2/§4.2 已改。
- **P2.1（window contract）**：`RatioCandidate` + writer 加 `window` 欄（§4.4）。
- **P2.2（period_kind filter）**：TTM 單季 net_income 限 `quarter_duration ∪ derived_q4`、明確排除 `ytd_duration`；BS endpoint 限 `instant_period_end`（§4.2）。

**§8 口徑**：2-point average / total_equity / year-ago topology / earliest-FY skip 全接受。`total_equity` caveat 會明寫進 `sec-financials-v2-schema.md` 與前端 tooltip：**是 total stockholders' equity（含 NCI、未扣 preferred），非 common equity**；common-equity 口徑留未來細修。

**Implementation gates（採用 Codex）**：
1. migration 加 `ttm_duration`（metrics-only）+ enum/docs 同步，當第一個 commit。
2. `ALL_RULE_IDS` + `DERIVE_ANALYTICS_RULE_IDS_FALLBACK` 同 commit 加 `RATIO_ROE`/`RATIO_ROA`（否則 drift test 紅）。
3. `ttm_duration` 前端路由**只**對 roe/roa（不無差別套全 RATIO）；維護一個明確的 TTM-ratio 清單。
4. annual BS endpoint 測試專門用 `Q4_FYyyyy` source、output `FYyyyy`。
5. **production `--apply` 前先 audit net_income lineage**（Codex 提醒）：抽樣 TTM 用的 4 季 net_income 必須是現行 adapter/derive-base 的 `quarter_duration`/`derived_q4`，不是 legacy parser silent-derive 藏在 facts 裡的值。雖然 ROE/ROA 不被 CF stale 擋，但 IS 單季 net_income 也可能是 stale-parse 產物——上線前要確認 lineage 乾淨，否則可能要等「re-parse 全 ticker 到現行 contract」那個 future 工程。

→ 設計收斂。先做 migration step，再 TDD 引擎。
