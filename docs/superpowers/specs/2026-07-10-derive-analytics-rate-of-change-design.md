# derive-analytics Growth→Rate-of-Change Design Spec

Date: 2026-07-10
Project scope: ai_agent（引擎 canonical 在 CC_Switch_Config）
Status: **v2 — post-argue（GPT-5.5 × Opus，7 輪 consensus，16/16 claims resolved）**。
v1→v2 併入：byte→數值等價、snapshot-upsert 現實、EPS-class guard、name-conditional
分支審計、tax-guard 更正、canonical key 對照與待修、近零爆炸值處置、下游白名單煙霧測試、
零刪除語意。Argue：`~/.config/argue/summary.md`（run `argue_1783687695918_162682`）。

把 derive-analytics 的「成長率」語意改成「**變動率**」(rate of change)：分母取絕對值，
負基期不再跳過；同時把變動率涵蓋科目從 5 個擴充到通用 IS 科目（Tier B，台美聯集）。
共用引擎（美股 + 台股同一套），影響 Supabase 生產 metrics；**前端顯示層本次不動**。

---

## 0. 動機

現行 `_growth_candidate`（`rules_crossperiod.py:427`）：`(cur − prior) / prior`，
guard `prior <= 0 → skip`。台燿 Q1_FY2023 淨虧損（net_income −206,348、eps −0.77）
→ Q1_FY2024 的 `net_income_yoy`/`eps_diluted_yoy`、Q2_FY2023 兩個 `_qoq`
共 4 格被跳過。使用者拍板（2026-07-10）：這族本該是「變動率」——變化幅度與方向都要呈現。

## 1. 公式改動（語意層）— 唯一數學觸點

`_growth_candidate`：

| | 現行 | 改後 |
|---|---|---|
| value | `(cv − pv) / pv` | `(cv − pv) / abs(pv)` |
| guard | `pv <= 0 → skip` | `pv == 0 → skip`（僅除零；float 精確等於 0，值皆為財報整數/兩位小數，無 epsilon 問題於此判斷） |
| formula 字串 | `(x@c − x@p) / x@p` | `(x@c − x@p) / abs(x@p)` |

**符號 = 分子方向（極性中立算術）**。pv>0 時 `abs(pv) ≡ pv`：
- **既有正基期 row 的「數值」不變**（§4 不變量 1，argue OK claim）。
- **但 formula 字串在所有 row 都變**（連正基期）→ 見 §4：不變量是**數值**等價，非 byte-identical。

負基期示例：−100→+100 = +2.00（轉盈）；−100→−50 = +0.50（虧損縮小=向上）；
−100→−200 = −1.00（虧損擴大=向下）；0→任何 = skip。

**近零基期（RISK，argue skeptic 0.90）**：`pv==0` 無 epsilon，極小非零基期會產出爆炸值
（eps 0.01→0.50 = +4900%）。**本次決定：如實輸出**（數學正確，符合「變動幅度都要呈現」原意）；
cap / N.M. 標記屬顯示層，**不在本 spec**。§8 明列此風險 + 供顯示層後續 cap。

**極性（好/壞）不在數字層**：引擎只算算術變動率。費用科目「+20%」= 費用增兩成（算術正確）；
好壞著色屬顯示層，本次不做（§7）。

## 2. 科目擴充 — GROWTH_METRICS 5 → 22（台美聯集）

Registry 為**聯集**；引擎逐 ticker 只對「facts 實際有的 uni_account」產 row（缺→靜默不產，
既有行為，`_GROWTH_OUT.get(uni)` None 即 continue）。每科目 × {yoy, qoq}，
uni_account/rule_id 由 generator 自動衍生（`{m}_{b}` / `RATIO_{M}_{B}`）。

### 2.1 ⚠️ DEFECT #1 — canonical uni_account key（實作前必先收斂）

**GROWTH_METRICS 的 key 必須逐字等於 facts 實際攜帶的 uni_account**（引擎按此查 fact），
且該拼法會被 generator 固化成永久 rule_id → **必須是全鏈唯一權威拼法**。
實測發現「schema 文件 vs 實際 parse 輸出」不一致，**須先裁定並修齊全部落點**才能寫 code：

| 語意 | 台股 facts 實測 | 美股 facts 實測 | schema 文件 (financials-view-schema) | 衝突 |
|---|---|---|---|---|
| SG&A（美） | —（台股拆 selling/g&a） | `selling_general_administrative`（GLW） | `selling_general_admin_expenses`（L247） | **文件≠parse** ⚠️ |
| 營業費用合計 | `total_operating_expenses`（台燿） | — | `operating_expenses`（L83） | **文件≠parse** ⚠️ |
| 營業外合計（美） | —（台股 non_operating_income_expense） | `other_nonoperating_income_expense`（GLW） | `other_nonoperating_income_expense`（L254） | 一致 ✅ |
| 推銷/管理/研發（台） | `selling_expenses`/`general_admin_expenses`/`research_and_development` | — | 同（L79,80） | 一致 ✅ |

**收斂規則（v2 拍板）**：以 **facts 實際輸出的拼法為權威**（引擎讀 facts，拼錯就查不到 fact、
產不出 row）。因此 registry 用 `selling_general_administrative`、`total_operating_expenses`。
**同時**在實作計畫加一步「schema 文件對齊」：把 `financials-view-schema.md` 的
`selling_general_admin_expenses`→`selling_general_administrative`、`operating_expenses`→
`total_operating_expenses` 更正（或反向，若裁定文件為權威則須先 re-parse——本 spec 選 parse 為權威，
因既有生產 facts 已用該拼法、改拼法代價過大）。**每個 growth key 都要在寫 code 前逐一 grep 確認
（extraction facts ∩ schema 文件 ∩ generator ∩ 兩 upsert fallback ∩ tests ∩ 下游）唯一。**

### 2.2 涵蓋清單（Tier B，22 metric；缺科目自動不產）

| 組 | uni_account（權威拼法 = facts 實測） | 台/美 |
|---|---|---|
| 既有 5（不變） | revenue, gross_profit, operating_income, net_income, eps_diluted | 台美共 |
| 主 P&L | cost_of_goods_sold, income_before_taxes, income_tax_expense, eps_basic | 台美共 |
| Opex（台拆） | selling_expenses, general_admin_expenses, research_and_development, expected_credit_loss, total_operating_expenses | 台 |
| Opex（美合） | selling_general_administrative | 美 |
| 營業外 | interest_income, interest_expense, other_gains_losses, non_operating_income_expense | interest_* 台美共；other_gains_losses/non_operating_income_expense 台；美對應 other_nonoperating_income_expense（見下） |
| NI 家族 | net_income_total_pre_nci, net_income_nci | 台美共（ir/無NCI 自動缺） |

> **註（parity 鐵律）**：`selling_expenses`（台）vs `selling_general_administrative`（美）是
> **不同語意科目**（拆分 vs 合併），各自 key 正確、非違反鐵律。台美**共同語意**科目
> （revenue/gross_profit/operating_income/cost_of_goods_sold/income_before_taxes/
> income_tax_expense/net_income/eps_*/interest_income/interest_expense/net_income_*）**同 key 同算法**。
> 美股營業外 `other_nonoperating_income_expense` 是否納入 GROWTH_METRICS：納入（聯集），
> 台股 `non_operating_income_expense` 與其為各自市場拼法、不強制同 key。
> → 共 22 個台側 + 2 個美側專屬（selling_general_administrative, other_nonoperating_income_expense）
> = registry 實際約 **24 個 uni_account**（聯集），rule_id 依 generator 衍生。**最終數字在
> 實作計畫 T0「canonical key 收斂」步定案並回填此表。**

### 2.3 排除
OCI 家族（oci_*, other_comprehensive_income, total_comprehensive_income,
comprehensive_income_*）、邊際率 pp 變動。

## 2b. DEFECT #2/#3 — EPS-class guard + name-conditional 分支審計

**現行**（`rules_crossperiod.py:480`）：`is_eps = uni == "eps_diluted"` —— derived_q4 的 Q4-approx
EPS 不還原 skip **只認 eps_diluted**。

- **DEFECT #2**：新增 `eps_basic` 同樣非加性 → 必須把 skip 擴到所有 EPS。
  改為 `is_eps = uni in ("eps_diluted", "eps_basic")`（或 class predicate `_is_per_share(uni)`）。
- **DEFECT #3 審計結論**：growth-emission path（`_emit_growth`/`_growth_candidate`/generator
  L137-146）中，**唯一** name-conditional 分支就是上述 `is_eps`；generator 與 candidate 本身
  metric-agnostic（`_GROWTH_OUT.get(uni)` 泛型查表）。→ 泛化該一處即完備；實作時仍須在 code review
  再掃一遍確認無其他隱藏 name 條件。

## 3. 絕不動清單（blast-radius 邊界；DEFECT #4 更正）

`rules_crossperiod.py` 其餘 negative-base guard 與「成長 vs 變動」無關，**一律不碰**：

- **ROE / ROA / ROIC**（L609,645 `avg <= 0`；及 **L568,571 是 ROIC 內 NOPAT 的 pretax/rate guard**）。
  **【DEFECT #4 更正】** v1 誤將 L568/571 說成 `effective_tax_rate` 的界限：實際 L568/571 屬 ROIC
  NOPAT 計算；`effective_tax_rate` 是 `rules_ratios.py` 的普通比率（L144-145 定義，L407-414 僅除零 skip、
  **無 rate 界限**，台燿實際輸出 1.713 為證）。兩者都不改。
- DSO/DIO/DPO/CCC、asset_turnover（`avg/ttm <= 0`）、interest_coverage、net_debt_to_ebitda
  （EBITDA ≤ 0）、全部 margins / current・quick・cash ratio / debt_to_equity / bvps / fcf / ebitda。

## 4. 不變量（測試 + rollout 必守）

**【DEFECT #5 修正】** upsert 是 **snapshot delete-then-reinsert**（`upsert_sec` L138-147、
`upsert_twse` L131-136 union payload+fallback 後刪該 scope 再插），**非 append-only**。既有 row
物理重寫，`provenance / updated_at / cell_id / formula 字串`都會 churn。因此：

1. **正基期「數值」等價**（NUMERIC）：既有 10 個 growth rule 的所有正基期 row，改前後
   `value` bit-identical（pv>0 時 `abs(pv)==pv`）。**不含** formula/provenance/updated_at
   （這些必然變）。
2. **非 growth metric「數值」零變動**：§3 清單所有 metric 的 `value` 改前後完全一致。
3. **Delta 僅二類**：(a) 既有 5 metric 的負基期格子 缺→有值（台燿實測恰 4 格）；
   (b) 新增科目的變動率 row。
4. `pv == 0` 仍 skip；`cur == 0, prior ≠ 0` 正常產出。
5. **EPS（basic+diluted）derived_q4 端點仍 skip**（§2b）。

## 5. 同步觸點（漏一個上庫被 gate 擋或測試紅）

| 觸點 | 動作 |
|---|---|
| **T0 canonical key 收斂**（DEFECT #1） | 逐 key grep facts∩schema∩generator∩2×fallback∩tests∩下游 → 定案唯一拼法 → 修 schema 文件 |
| `_growth_candidate`（L427,440） | value `/abs(pv)`、guard `pv==0`、formula 字串、docstring |
| `is_eps` guard（L480） | `== "eps_diluted"` → `in {eps_diluted, eps_basic}`（DEFECT #2/#3） |
| GROWTH_METRICS（L137） | 5 → 22（權威拼法，聯集） |
| 註解 L120-121 + **stale L134-136「3 pre-existing」**（實為 10）| 更正措辭為 rate-of-change + 正確數 |
| `ALL_CROSSPERIOD_RULE_IDS` | generator 自動衍生 → 確認含全部新 rule_id |
| `upsert_sec_financials.py` FALLBACK（L90） + `upsert_twse_financials.py` FALLBACK（L92）| +新 rule_id（數在 T0 定案） |
| **既有測試硬編 10 growth rule** | 更新為新集合（RISK：不改則紅）|
| `SKILL.md` + 舊 spec 2026-06-02 §8.D | 語意更新為變動率 |
| `financials-view-schema.md` | 登記新 rule/uni_account + T0 的拼法更正 |
| 前端 `constants.ts` | **不動**（但見 §7：既有 5 的負基期格子仍會在現有 UI 冒出來）|
| **compose-financials + wiki-ingest-{sec,mops}-10k** | **不改 code，但 rollout 要煙霧測試**：確認它們白名單挑 key，非疊代 derived 區塊（RISK：否則 17 新 row 漏進 Financials.md / wiki，未知 rule_id 可能渲成原始 id）|

## 6. Rollout（生產紀律）

1. **T0**：canonical key 收斂（§2.1）+ schema 文件對齊。
2. TDD 改引擎（canonical `~/CC_Switch_Config/skills/derive-analytics/`，含 §2b EPS guard；
   sync-to-local）；**新增近零/轉盈虧/負基期測試**（涵蓋 eps/interest/non-op/NCI 高噪音線）。
3. 本機重跑 derive-analytics：美股（INTC/AAOI/SNDK/LITE/MU/GLW）+ 台股（3081/2308/6274）；
   **改前 output 先備份**。
4. **不變量驗證 = NUMERIC-ONLY + DB 層 + upsert 後**：比對 `value`，**排除**
   formula/provenance/updated_at/cell_id（否則 provenance churn 誤報回歸）。呈使用者。
5. **逐 ticker 授權** re-upsert（dry-run diff 先看；理解為 snapshot 重寫、非純加）。
6. **下游煙霧測試**：compose / wiki-ingest 各跑一檔，確認新 row 未漏進顯示產物。
7. 文件收尾 + memory。

## 7. Out of scope
- 前端顯示層全部（標籤「成長率→變動率」、新 metric 顯示行、polarity 紅綠、近零 cap/N.M.）。
  **註**：既有 5 metric 的負基期格子改後會在現有 UI 出現（原本空白）→「backend-only」不等於
  「畫面零變化」（argue RISK），須先看前端消費行為再宣稱。
- 顯示層 metric 極性註冊表（費用增=壞、營外方向）——未來另一 spec。
- OCI 變動率、margin-pp 變動、derive-base。

## 8. 風險與緩解

| 風險（argue 來源） | 緩解 |
|---|---|
| 近零基期爆炸 %（skeptic 0.90） | 如實輸出（正確）；顯示層 cap/N.M. 另案；§6 加近零測試 |
| 「backend-only」畫面仍變（skeptic 0.88） | §7 註明；rollout 先確認前端消費 |
| compose/wiki 漏出新 row（skeptic 0.86） | §5/§6 煙霧測試白名單 |
| 零刪除：某新 rule 之後產 0 row → snapshot 刪其舊 row（skeptic 0.88） | owned-scope 正確行為；§4/§8 明載「新 rule 的 stale row 於 rerun 可能被刪」，非永久保留 |
| NCI/non-op/interest 為最高噪音線（skeptic 0.78） | 使用者選 Tier B 保留；§6 加近零測試 + code review 標高審 |
| DB 無 rule_id enum 擋新 id（skeptic 0.82） | 已查無 CHECK；仍須更新 2×fallback + tests |
| formula/provenance 誤判為回歸 | §6 numeric-only 比對 |
