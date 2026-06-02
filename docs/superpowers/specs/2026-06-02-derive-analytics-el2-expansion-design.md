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

所有階段沿用 ROE/ROA 的 storage contract：quarterly = `period_kind='ttm_duration'` + `provenance.window='TTM'`、annual = `fy_annual_duration`；statement=RATIO；GAAP only；facts-wins guard 不變。

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
