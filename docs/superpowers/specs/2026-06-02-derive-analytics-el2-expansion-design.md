# derive-analytics EL2 擴充（效率比 + YoY + ROIC）Design Spec / Codex Review

Date: 2026-06-02 / Project: ai_agent
Status: 設計待 Codex review（尚未寫 code）。前置 EL2 引擎（ROE/ROA）已上 production + 4 輪 Codex 收斂；`ttm_duration` migration 已 apply。本 spec 在**同一引擎**上加三批指標。
背景：`docs/superpowers/specs/2026-06-01-derive-analytics-el2-cross-period-design.md`（ROE/ROA 起手）§0–§13。

> 給 GPT/Codex review **設計**。請挑戰口徑、新 uni_account、單位/前端 contract、與既有引擎邊界。
> **保持質疑**：以下是我的判斷與預設選擇，請挑戰；同意才實作。

---

## 0. 範圍 & 共用引擎

EL2 三個積木（已就緒）：①TTM 加總 ②期初期末 2 點平均餘額 ③去年同期 lookup。ROE/ROA 用了 ①②。本 spec：
- **階段 1 — 效率/周轉**：asset turnover + DSO/DIO/DPO + CCC（積木①②，與 ROE/ROA 同形狀）。
- **階段 2 — YoY 成長率**：revenue/net_income/EPS YoY（積木③，新 candidate 形狀）。
- **階段 3 — ROIC**：TTM NOPAT ÷ 平均 invested capital（積木①②，composite 分子分母）。
- **階段 4（不在本 spec）— EBITDA 家族**：卡 D&A re-parse（INTC/AAOI/SNDK）+ NLM 定義確認，另立 spec。

storage contract（**per-phase，非全階段一致** — Codex P2 修正，見 §8）：
- **階段 1/3（TTM 比率）**：quarterly = `period_kind='ttm_duration'` + `provenance.window='TTM'`、annual = `fy_annual_duration`。
- **階段 2（YoY）**：quarterly = `quarter_duration`（單季 vs 去年同季）、annual = `fy_annual_duration`；**不用 ttm_duration**。
- 共同：statement=RATIO；`unit='Pure'`（days/x/pct 都是 Pure 下的 display category，非 storage unit）；GAAP only；facts-wins guard 不變。

---

## 階段 1 — 效率/周轉比

### 1.1 指標與口徑

| 指標 | uni_account | 公式（quarterly = TTM flow / 2點平均餘額）| 單位 |
|---|---|---|---|
| 資產周轉 | `asset_turnover` | revenue_TTM ÷ avg(total_assets) | **x**（倍）|
| 存貨天數 | `dio` | 365 × avg(inventories) ÷ cogs_TTM | **days** |
| 應收天數 | `dso` | 365 × avg(accounts_receivable) ÷ revenue_TTM | **days** |
| 應付天數 | `dpo` | 365 × avg(accounts_payable) ÷ cogs_TTM | **days** |
| 現金循環 | `ccc` | dio + dso − dpo | **days** |

annual 版：flow 用 FY 值、餘額用 `Q4_FY{y-1}`/`Q4_FY{y}` 2 點平均（與 ROE/ROA annual 完全一致）。

### 1.2 決策點（請 Codex 拍板）

1. **出 days 還是 turnover？（我選 days + asset_turnover）**
   - 存貨/應收/應付：出**天數**（DIO/DSO/DPO），不另出 inventory/receivables/payables_turnover（它們 = 365/days，純倒數冗餘）。理由：天數是實務最常引用、且 CCC 直接相加。
   - 資產：出 **asset_turnover（x）**（無天數對應、是 DuPont 拆解項）。
   - **替代方案**：也出 4 個 turnover(x)（共 8 指標）。我傾向不要（冗餘 + 多 4 個 uni_account）。同意 days-only（+asset_turnover）嗎？

2. **days 基數 = 365（固定）**。52/53 週財年 TTM 視窗實際 364–371 天，用固定 365 有 ≤1.6% 誤差。替代：用實際視窗天數（period_end − period_start，period_start 我們已存）。我傾向**固定 365**（業界慣例、可比性高、簡單），把 52/53 週誤差列 known limitation。要改用實際天數嗎？

3. **餘額用平均（與 ROE/ROA 一致）還是期末？** DSO/DIO/DPO 教科書多用**平均餘額**（流量對應平均存量），我選平均（引擎一致）。實務有用期末單點的（反映當下）。同意平均嗎？

4. **payables 用 COGS 當採購代理**（標準做法，缺真實 purchases）。同意嗎？

5. **CCC 可為負**（Apple/Dell 式，good）→ emit 負值。CCC 需同期 DIO+DSO+DPO 三者都算得出，缺一 → skip CCC（第二 pass 合成）。

6. **新 uni_account（5 個）**：`asset_turnover` / `dio` / `dso` / `dpo` / `ccc` → 要在 schema §2.x 登記為確認 core key。

7. **前端新單位 "days"**：turnover 沿用既有 multiple 顯示（`4.37x`）；days 是**新顯示類別**（例 `45 days` 或 `45d`，pct/multiple 之外第三類）。`value` 仍存 Pure 數值（天數），前端加 `RATIO_AS_DAYS` set + 格式。skip：分母（TTM flow）≤ 0 → skip（負毛利/負營收無意義）。

### 1.3 引擎改動

`rules_crossperiod.py`：把 flow 索引從 hardcode `net_income` **泛化**成任意 IS flow（net_income / revenue / cost_of_goods_sold），用 `(version, uni, (y,q))` / `(version, uni, y)` 索引。`CrossPeriodRule` 加 `output_kind`（`ratio`=flow/avg、`days`=365×avg/flow）+ `unit`。CCC 用第二 pass 合成（讀同期 dio/dso/dpo candidate）。`ALL_CROSSPERIOD_RULE_IDS` union 新 rule_id。

---

## 階段 2 — YoY 成長率

### 2.1 指標與口徑

| 指標 | uni_account | 公式 | 單位 |
|---|---|---|---|
| 營收 YoY | `revenue_yoy` | (current − year_ago) / \|year_ago\| | **pct** |
| 淨利 YoY | `net_income_yoy` | 同上 | pct |
| EPS YoY | `eps_diluted_yoy` | 同上 | pct |

- **quarterly**：current 單季 vs 去年同季（Q3_FY2025 vs Q3_FY2024），`period_kind='quarter_duration'`，period=current 季。**不是 TTM-vs-TTM**（單季 YoY 是最常引用的「營收年增 X%」）。
- **annual**：FY vs 前一 FY，`period_kind='fy_annual_duration'`。

### 2.2 決策點

1. **新 candidate 形狀**：不是 flow/balance ratio，而是**同一 uni_account 跨兩期的成長率**。分子=current−year_ago、分母=|year_ago|。這跟 EL2 既有 rule（TTM/avg）不同 path，我打算放 `rules_crossperiod.py` 內新 section（或新 module）。
2. **負/零基數 → N/M skip**：year_ago ≤ 0 → skip（從虧損/零成長率無意義；EPS 由負轉正不出 %）。同意嗎？
3. **quarterly 用單季 vs TTM**：我選**單季 YoY**（period_kind=quarter_duration，非 ttm_duration）。注意：這會讓 RATIO quarterly view 同時有 quarter_duration（YoY）、ttm_duration（ROE/turnover）、instant（流動比）——前端路由要能容納（已有多 period_kind 並存機制）。同意單季嗎？還是要 TTM YoY？
4. **指標集**：先做 revenue/net_income/eps_diluted 三個 headline。要不要也加 gross_profit/operating_income YoY？我傾向先三個。

---

## 階段 3 — ROIC

### 3.1 口徑

**ROIC = TTM NOPAT ÷ 平均 invested capital**
- **NOPAT** = TTM operating_income × (1 − tax_rate)。
- **invested capital** = total_equity + 有息負債 − (cash + short_term_investments)。有息負債 = `short_term_borrowings` + `current_portion_of_long_term_debt` + `long_term_debt`（沿用 EL1 debt_to_equity 的 debt terms）。
- 平均 = 2 點（期初/期末 invested capital），分子 NOPAT 用 TTM/FY。

### 3.2 決策點（最重，定義分歧大）

1. **tax_rate 取哪個？** 選項：(a) TTM effective tax rate（= TTM tax ÷ TTM pretax，內生、隨期波動）(b) 法定 21%（穩定但與實際脫節）。我傾向 **(a) TTM effective**（內部一致、不引外部假設），但要處理 pretax ≤ 0 或 tax rate 異常（如負稅率）→ 該期 ROIC skip 或 clamp？我傾向 pretax ≤ 0 → skip。
2. **invested capital 定義（三大流派，選一）**：
   - (A) **Financing 視角**：equity + 有息債 − 現金（我選這個，排除超額現金的營運投入資本）。
   - (B) total_assets − current_liabilities（operating capital）。
   - (C) equity + 有息債（不扣現金）。
   - 我選 **(A)**。請挑戰：要不要扣 short_term_investments（我有扣）？cash 全扣還是只扣超額現金（後者需假設，我傾向全扣）。
3. **新 uni_account**：`roic`（pct）+ 可能 `nopat`（absolute，USD）要不要也存？我傾向**只存 roic**（nopat 是中間量，放 provenance.inputs 即可，不另開 core key）。
4. **skip**：avg invested capital ≤ 0 → skip；TTM 湊不滿/缺餘額 → skip；pretax ≤ 0（tax rate 無意義）→ skip。

---

## 4. 跨階段：storage / 前端 / 測試 contract

- **period_kind**：階段 1/3 = ttm_duration（quarterly）/ fy_annual_duration（annual），沿用既有 migration（無新 migration）。階段 2 = quarter_duration / fy_annual_duration（YoY 用既有 kind，無新 migration）。
- **period_start**：階段 1/3 沿用 `_day_after(begin_f.period_end)`。階段 2 YoY 的 period_start = current 期自己的 period_start（單季/FY，非跨期視窗）。
- **單位**：pct（YoY/ROIC）、x（asset_turnover）、days（DSO/DIO/DPO/CCC，新）。前端 `RATIO_AS_DAYS` 新增。
- **facts-wins**：全為 RATIO statement，與既有 guard 一致。
- **drift guard / ALL_*_RULE_IDS**：每階段 union 新 rule_id；5 mirror drift test 涵蓋。
- **upsert fallback**：`DERIVE_ANALYTICS_RULE_IDS_FALLBACK` += 新 rule_id。

## 5. 實作順序（依風險）

1. 階段 1 效率比（最機械，純引擎泛化）→ ship → Codex review。
2. 階段 2 YoY（新 candidate 形狀）→ ship → review。
3. 階段 3 ROIC（定義最重）→ ship → review。
4. 階段 4 EBITDA（待 re-parse + NLM）→ 另 spec。

## 6. 請 Codex 裁示的核心問題（彙整）

1. 效率比 days-only（+asset_turnover）vs 8 個都出？
2. days 基數固定 365 vs 實際視窗天數？
3. DSO/DIO/DPO 用平均餘額 vs 期末？
4. YoY quarterly 用單季 vs TTM？負基數 skip？
5. ROIC：tax rate（TTM effective vs 法定）、invested capital 定義（A/B/C）、扣現金與否？
6. 新 uni_account（asset_turnover/dio/dso/dpo/ccc/revenue_yoy/net_income_yoy/eps_diluted_yoy/roic）登記為 core key — 同意命名嗎？

---

## 7. Codex Review（2026-06-02）

結論：大方向同意，可以照「Phase 1 efficiency → Phase 2 YoY → Phase 3 ROIC」拆段開工；但 spec 目前有幾個 contract gap，實作前要折回 body，否則會出現「有算出 row、前端不顯示」或「period_start 寫不出來」這類錯誤。

### Findings

**P2 - §0 / §4 的 period_kind contract 前後矛盾。**

§0 寫「所有階段沿用 ROE/ROA storage contract：quarterly = `ttm_duration`」，但 §2/§4 又正確地把 YoY quarterly 定為 `quarter_duration`。這要改成：**Phase 1/3 quarterly 用 `ttm_duration`；Phase 2 YoY quarterly 用 `quarter_duration`**。否則 runner / frontend routing 容易被錯誤的一句總則帶偏。

**P2 - §4 的 YoY `period_start = current 期自己的 period_start` 目前不可實作。**

現有 `_shared.sec_json_adapter.FactRow` 只有 `period_end`，沒有 duration `period_start`；ROE/ROA 最後能補 `period_start` 是靠 opening BS instant + 1 day，不是從 IS fact 讀 startDate。YoY 的 `quarter_duration` / `fy_annual_duration` 若要拿 current fact 的 start，目前沒有欄位可拿。建議本階段 **YoY `period_start=None`**，只保留 `period_end=current.period_end`；若未來 parse 層開始抽 XBRL duration startDate，再做 table-wide backfill。不要為 YoY 用 label 猜起始日。

**P2 - `ttm_duration` 前端 allowlist 目前只有 `roe/roa`，Phase 1/3 必須同步擴。**

`useFinancialMatrix` 目前故意只允許 `TTM_RATIO_ROWS = {roe, roa}` 的 `ttm_duration` row 進 quarterly RATIO grid。新增 `asset_turnover/dio/dso/dpo/ccc/roic` 時，這個 allowlist 必須擴成明確的 TTM-ratio 清單；YoY 不加進去。這是顯示 contract，不是 optional polish。

**P2 - days 不是新的 storage unit；應明確寫成 Pure 下的 display category。**

目前 schema/rules 的 RATIO contract 是 `unit='Pure'`，前端再用 `RATIO_AS_MULTIPLE` 把倍數從百分比裡拆出來。§1.2/§4 寫「days 單位」容易讓人以為要把 DB `unit` 寫成 `days`；這會撞到 canonical unit 文件與 adapter 習慣。建議維持 **storage `unit='Pure'`、semantic/display 由 `RATIO_AS_DAYS` 決定**，並同步更新 `fmtValue()` / `chartGroupOf()` / docs：`Pure` 現在分 pct-style、multiple-style、days-style 三類。若真的要 storage `unit='days'`，那就是另一個 canonical-unit migration/spec，不要混在本次。

**P2 - ROIC invested-capital terms 要補 required/optional policy。**

§3 定義了公式，但沒有說缺項怎麼處理。建議定成：

- `total_equity` required。
- `cash_and_cash_equivalents` required；缺 cash 時不要算 net invested capital。
- `short_term_investments` optional-as-0。
- debt terms 沿用 `debt_to_equity`：三項 optional-as-0 + exact-value dedup，因為無債公司是真實 0 債；但若有 parse coverage caveat，要寫進 known limitation。
- begin/end invested capital 都要能算且 avg > 0，否則 skip。

**P3 - YoY 公式文字與 skip policy 要一致。**

表格寫 `(current - year_ago) / |year_ago|`，但決策又要求 `year_ago <= 0` skip。若採 skip，公式就寫 `(current - year_ago) / year_ago` 並要求 prior > 0；`abs()` 只在允許負基數時才有意義。

### 六個決策點

1. **效率比：同意 days-only + asset_turnover。** DIO/DSO/DPO 用 days，CCC 直接相加；不要同時 materialize inventory/receivables/payables turnover，避免倒數冗餘。`asset_turnover` 保留，因為它是 DuPont 項且沒有 days 對應。

2. **days 基數：同意固定 365。** 這是最常見 vendor/教科書口徑，可比性比 52/53 週實際天數更重要。本 spec 可把 52/53 週誤差列 known limitation；不需要引入 actual-window-days branch。

3. **DSO/DIO/DPO：同意用平均餘額。** 流量對平均存量是正確基準，也跟 ROE/ROA EL2 引擎一致。期末餘額可以是未來 variant，但不應混進 core key。

4. **YoY：同意 quarterly 用單季、annual 用 FY；prior <= 0 skip。** 單季 YoY 才符合一般「營收年增」語義。從負數/零基數轉正的 % 沒有穩定解讀，skip 比輸出巨大百分比更好。實作上請把 YoY path 跟 TTM path 分開，不要把 YoY 放進 `ttm_duration`。

5. **ROIC：採 TTM effective tax + invested-capital A，但異常 tax rate 不要 clamp。**  
   - tax_rate = TTM tax / TTM pretax；pretax <= 0 skip。
   - 若 tax_rate < 0 或 > 1，建議 skip，而不是 clamp；clamp 會默默改寫經濟意義。
   - invested capital 用 A：equity + interest-bearing debt - cash - short_term_investments。cash 全扣可接受，因為「超額現金」需要外部假設；把 cash-rich 公司 ROIC 可能被墊高/分母變小列 caveat。
   - 不 materialize `nopat`，只放在 `roic` provenance/formula 裡。

6. **uni_account 命名：接受。**  
   `asset_turnover/dio/dso/dpo/ccc/revenue_yoy/net_income_yoy/eps_diluted_yoy/roic` 可登記為 core key。前端 label 請展開 DIO/DSO/DPO/CCC 的全名；YoY 名稱不必加 `_pct`，但必須在 docs/formatter 中明確歸為 pct-style。

### Implementation Gates

- Phase 1 開工前，先把 spec body 補正：Phase 1/3 vs Phase 2 的 period_kind、YoY period_start、days storage/display、ROIC required/optional policy。
- Phase 1 ship gate：新增 `RATIO_AS_DAYS`、擴 `TTM_RATIO_ROWS`、`chartGroupOf()` 不把 days 和 pct/multiple 混軸，並用 preview 或 unit test 驗 `ttm_duration` efficiency rows 能顯示。
- Phase 2 ship gate：驗 YoY rows 是 `quarter_duration` / `fy_annual_duration`，不出 `ttm_duration`，且 prior <= 0 cases skip。
- Phase 3 ship gate：ROIC tax-rate abnormal cases（pretax<=0、tax<0、tax>pretax、avg invested capital<=0）都要有測試。

---

## 8. Claude 收斂 — body 補正（2026-06-02，對齊 Codex §7）

6 個決策點 Codex 全同意；5 個 P2 + 1 P3 我**逐項質疑後全接受**（都是 contract 一致性 / 資料模型現實，無 overreach）。以下為補正後的**權威 contract**，實作以此為準（§0 已同步改）：

**A. period_kind（per-phase，取代 §0 原本的全階段一致誤述）**
- 階段 1/3：quarterly `ttm_duration`（+`window='TTM'`）、annual `fy_annual_duration`。
- 階段 2 YoY：quarterly `quarter_duration`、annual `fy_annual_duration`。**YoY path 與 TTM path 程式上分開**，YoY 永不出 `ttm_duration`。

**B. days 是 `Pure` 下的 display category，不是 storage unit**
- DB `unit` 一律 `Pure`（與既有 RATIO contract 一致）。display 由前端 set 決定：`RATIO_AS_MULTIPLE`（x）、新增 `RATIO_AS_DAYS`（DSO/DIO/DPO/CCC）、其餘 pct-style。
- `fmtValue()` / `chartGroupOf()` / canonical-unit docs 同步：`Pure` 現分 pct / multiple / days 三類顯示；days 不與 pct/multiple 混軸。
- 若未來真要 storage `unit='days'` → 另開 canonical-unit migration，不混本次。

**C. YoY period_start = None（FactRow 無 duration startDate）**
- 現有 `FactRow` 只有 `period_end`；ROE/ROA 的 period_start 是靠 opening BS instant + 1 day（balance-window），YoY 不是 balance-window、拿不到。→ YoY rows `period_start=None`、`period_end=current.period_end`，**不用 label 猜起始日**。未來 parse 層抽 XBRL duration startDate 再 table-wide backfill。

**D. YoY 公式與 skip 一致**
- prior > 0 才算（prior ≤ 0 → skip）；分母用 `year_ago`（非 `|year_ago|`），公式 = `(current − year_ago) / year_ago`。`abs()` 僅在允許負基數時才有意義，本階段不允許。

**E. 前端 `ttm_duration` allowlist 擴充（顯示 contract，非 polish）**
- `TTM_RATIO_ROWS` 從 `{roe, roa}` 擴成明確清單，加入 `asset_turnover/dio/dso/dpo/ccc/roic`（階段 1/3）。YoY **不加**（它是 quarter_duration）。

**F. ROIC required/optional policy + abnormal tax skip**
- required：`total_equity`、`cash_and_cash_equivalents`、`operating_income`、tax/pretax（算 effective rate）。
- optional-as-0：`short_term_investments`、債務三項（`short_term_borrowings` + `current_portion_of_long_term_debt` + `long_term_debt`，exact-value dedup，沿用 `debt_to_equity`）。
- invested capital A = equity + 有息債 − cash − short_term_investments；avg ≤ 0 → skip。
- tax_rate = TTM tax / TTM pretax；**pretax ≤ 0 → skip；tax_rate < 0 或 > 1 → skip（不 clamp，clamp 會默默改寫經濟意義）**。
- 不 materialize `nopat`（放 roic provenance/formula）。cash 全扣的 cash-rich 墊高效應列 caveat。

**G. 前端 label**：DIO/DSO/DPO/CCC 展開全名；YoY 名稱不加 `_pct` 但 docs/formatter 明確歸 pct-style。

**實作順序不變**：階段 1（效率，含 §6276fdd flow-index 泛化已就緒）→ 2（YoY）→ 3（ROIC），各自過 §7 ship gate 後 Codex functional review。
