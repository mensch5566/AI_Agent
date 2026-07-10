# derive-analytics Growth→Rate-of-Change Design Spec

Date: 2026-07-10
Project scope: ai_agent（引擎 canonical 在 CC_Switch_Config）
Status: v1 draft — 待 argue（GPT-5.5 × Opus）收斂。

把 derive-analytics 的「成長率」語意改成「**變動率**」(rate of change)：分母取絕對值，
負基期不再跳過；同時把變動率涵蓋的科目從 5 個擴充到**全部通用 IS 科目（Tier B，台美聯集）**。
共用引擎（美股 + 台股同一套），影響 Supabase 生產 metrics；**前端顯示層本次不動**。

---

## 0. 動機（來自台燿 6274 實例）

- 現行 `_growth_candidate`（`rules_crossperiod.py:427`）：`(cur − prior) / prior`，
  guard `prior <= 0 → skip`。Q1_FY2023 台燿淨虧損（net_income = −206,348、eps = −0.77）
  → Q1_FY2024 的 `net_income_yoy` / `eps_diluted_yoy` 與 Q2_FY2023 的兩個 `_qoq`
  共 4 格被跳過。任何有虧損季的公司（INTC 等）同樣缺格。
- 使用者拍板（2026-07-10）：這族指標的語意本來就該是「變動率」不是「成長率」——
  **變化幅度與方向都要呈現**，前 −100 → 今 +100 就是 +200%。

## 1. 核心公式改動（語意層）

`_growth_candidate`（唯一觸點）：

| | 現行 | 改後 |
|---|---|---|
| 公式 | `(cv − pv) / pv` | `(cv − pv) / abs(pv)` |
| guard | `cv is None or pv is None or pv <= 0 → skip` | `cv is None or pv is None or pv == 0 → skip` |
| formula 字串 | `(x@cur - x@prior) / x@prior` | `(x@cur - x@prior) / abs(x@prior)` |

**符號慣例（極性中立的算術方向）**：結果符號 = 分子方向。基期正時 `/abs(pv) ≡ /pv`
→ **既有正基期值 byte-identical（零回歸）**。負基期示例：

| prior → cur | 值 | 讀法 |
|---|---|---|
| −100 → +100 | +2.00 | 轉盈，+200% |
| −100 → −50 | +0.50 | 虧損縮小（算術向上） |
| −100 → −200 | −1.00 | 虧損擴大（算術向下） |
| 0 → 任何 | skip | 除以零無定義（唯一仍跳過的情況） |

**極性（好/壞）不在數字層**：引擎只算算術變動率，不編碼「增加=好」。
費用類科目「+20%」= 費用增兩成（算術正確）；好壞著色屬顯示層，**本次不做**（§7）。

## 2. 科目擴充（涵蓋層）— GROWTH_METRICS 5 → 22（台美聯集）

Registry 是**聯集**；引擎逐 ticker 只對「facts 裡實際存在的 uni_account」產 row，
缺科目自動不產（不報錯、不產 null）。每個科目 × {`yoy`, `qoq`} 兩個 basis，
uni_account/rule_id 依既有 generator 慣例自動衍生（`{m}_{b}` / `RATIO_{M}_{B}`）。

| 組 | uni_account | 備註 |
|---|---|---|
| 既有 5（不變） | revenue, gross_profit, operating_income, net_income, eps_diluted | uni_account/rule_id byte-identical |
| 主 P&L | cost_of_goods_sold, income_before_taxes, income_tax_expense, eps_basic | |
| Opex 細項（台） | selling_expenses, general_admin_expenses, research_and_development, expected_credit_loss, total_operating_expenses | 美股無此拆法 → 自動不產 |
| Opex（美） | selling_general_administrative | 台股無 → 自動不產 |
| 營業外（台） | interest_income, interest_expense, other_gains_losses, non_operating_income_expense | interest_* 台美皆有 |
| 營業外（美） | other_nonoperating_income_expense | |
| NI 家族 | net_income_total_pre_nci, net_income_nci | ir filer 自動缺 → 不產 |

共 22 metric × 2 basis = **44 個 rule_id**：既有 10（5 metric × 2 basis），新增 34（17 × 2）。

**排除**（使用者拍板）：OCI 家族（oci_*, other_comprehensive_income,
total_comprehensive_income, comprehensive_income_*）——波動大、基期常近零、非營運科目。
邊際率的 pp 變動（gross_margin_pct 等）＝不同語意，另案。

## 3. 絕不動清單（blast-radius 邊界）

`rules_crossperiod.py` 其餘 negative-base guard 是**比率自身的財務防呆**，與「成長 vs 變動」
無關，**一律不碰**：

- ROE / ROA / ROIC（`avg <= 0` skip；對負淨值/資本算報酬無意義）
- effective_tax_rate（pretax ≤ 0 skip、rate 界限）
- DSO / DIO / DPO / CCC、asset_turnover（`avg/ttm <= 0` skip）
- interest_coverage、net_debt_to_ebitda（EBITDA ≤ 0 skip）
- 全部 margins / current・quick・cash ratio / debt_to_equity / bvps / fcf / ebitda
  （無 prior-base 概念，本改動觸不到）

## 4. 不變量（測試必守）

1. **正基期零回歸**：既有 10 個 growth rule 的所有正基期 row，改前後 byte-identical
   （value / uni_account / rule_id / inputs / formula 除措辭外的數值部分）。
2. **非 growth metric 零變動**：§3 清單 22 個 metric 的輸出，改前後完全一致。
3. **Delta 僅二類**：(a) 既有 5 metric 的負基期格子由缺→有值；
   (b) 新增 17 個 metric 的變動率 row。台燿 29 期實測基準：(a) 恰 4 格
   （Q2_FY2023 net_income/eps_diluted_qoq、Q1_FY2024 net_income/eps_diluted_yoy）。
4. `prior == 0` 仍 skip；`cur == 0, prior ≠ 0` 正常產出（值 = −1.0 或依符號）。

## 5. 同步觸點（漏一個就上庫被 gate 擋 — 此前踩過）

| 觸點 | 動作 |
|---|---|
| `rules_crossperiod.py` GROWTH_METRICS | 5 → 22（聯集清單） |
| `_growth_candidate` | 公式 + guard + formula 字串 + docstring（§1） |
| L120–121 註解 & spec 引用 | 「prior > 0 required」改為 rate-of-change 語意 |
| `ALL_CROSSPERIOD_RULE_IDS` | generator 自動衍生 → 確認含 44 個 |
| `upsert_sec_financials.py` `DERIVE_ANALYTICS_RULE_IDS_FALLBACK` | +34 rule_id |
| `upsert_twse_financials.py` `DERIVE_ANALYTICS_RULE_IDS_FALLBACK` | +34 rule_id |
| derive-analytics `SKILL.md` + 舊 spec（2026-06-02 §8.D）交叉註記 | 語意更新為變動率 |
| `docs/financials-view-schema.md` | 登記 34 個新 rule/uni_account |
| 前端 `constants.ts` | **不動**（新 metric 進 DB 不顯示；additive、非 breaking） |
| wiki-ingest-* | 不改 code；讀 analytics 自動見新 metric，渲染由該 skill 自理 |

## 6. Rollout（生產紀律）

1. TDD 改引擎（canonical `~/CC_Switch_Config/skills/derive-analytics/`，改完 sync-to-local）。
2. 本機重跑 derive-analytics：**美股全部已上庫 ticker（INTC/AAOI/SNDK/LITE/MU/GLW）+ 台股
   （3081/2308/6274）**；跑不變量 §4 的 diff 驗證（改前 output 先備份供 byte-diff）。
3. 驗證報告呈使用者 → **逐 ticker 授權** re-upsert 生產 Supabase（純加 row + 既有 row 零變動，
   dry-run diff 先看）。
4. 文件收尾（§5 表列）+ memory。

## 7. Out of scope

- 前端顯示層一切（標籤「成長率→變動率」文案、新 metric 的顯示行、polarity 紅綠著色）。
- 顯示層 metric 極性註冊表（費用增=壞、營外收益方向等）——未來另一 spec；
  本 spec 只保證數字層算術中立，極性不進 derive。
- 邊際率 pp 變動、OCI 變動率。
- derive-base（單季重建）不涉及。

## 8. 風險與緩解

| 風險 | 緩解 |
|---|---|
| 負基期變動率被誤讀成傳統成長率 | formula 字串明示 `abs()`；provenance inputs 帶基期原值（含負號）；顯示層文案另案 |
| 新科目在部分 ticker 產生大量 row | 純 additive；upsert dry-run 先看量；gate 檔案同步（§5） |
| 兩個 upsert fallback 漏加 | §5 明列 + 計畫中設驗證步（registry 數 == fallback 數） |
| 極端小基期（|prior| 很小）產生巨大 % | 如實呈現（數學正確）；顯示層若要 cap/N.M. 標記屬另案 |
