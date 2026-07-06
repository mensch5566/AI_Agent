# Phase E — 台股上庫 + 網頁前端 + NLM 核對 (spec)

Date: 2026-07-05
Scope: 把台股（TWSE iXBRL）財報從本地 JSON 打通到 Supabase + Next.js Financial Viewer，並用 NotebookLM 逐數字核對。先做聯亞 3081，過關再做台達電 2308（含補 parse）。
Goal（user）：台股網頁前端搭好，且跟 NLM 核對財報中每個數字都對上；聯亞過關就把台達電從 parse 到前端做完並一樣 NLM 驗收。

Iron laws（不變）：數字 100% 精準、只走統一管道寫 Supabase（禁直接 INSERT/UPDATE）、production write（`--apply`）需 user 逐次授權、parse/compose 不運算、台美最終三表 uni_account + derive 指標一致。

---

## 0. 現況（recon 已證，file:line 見兩份 recon report）

- **Schema 已 market-agnostic**：`sec_financial_companies.currency`（default USD）、facts/metrics/dimensional 每筆帶 `unit`（`TWD_thousands` / `TWD_per_share` …）。**無 market 欄，但 ticker namespace 天然不相交**（US=字母、TW=4 位數字），且 `exchange`/`currency` 已自描述 → **MVP 零 migration**（Option 2）。
- **Upsert 缺台股腳本**：`scripts/upsert_sec_financials.py` 路徑硬編 SEC Filings + parse-10QK-gaap 等。需新 `upsert_twse_financials.py`（~90% mirror）。
- **`_shared/twse_json_adapter.py` 已有** `adapt_company_twse()`（exchange=TWSE/currency=TWD/cik=""）+ `adapt_twse_facts()`（FactRow）。
- **3081 本地資料齊全且新鮮**（2026-07-02）：parse-twse-ixbrl facts（report_category=ir/個體, 2043 facts）、derive-base 349、derive-analytics 874。
- **前端 API `/api/financials/[ticker]` 已 market-agnostic**（純 by ticker 查同一批表）。前端阻塞點：formatter 硬編 USD/$；BS_ROWS 缺 3 條台股權益列；KNOWN_TICKERS 硬編。`net_income_nci` 前端已有。
- **NLM 3081 cross-check config 齊備**：notebook `c8155033…`（work profile）、17 期 Separate PDF source_id 已填、label_to_key 126 條。

---

## 1. 決策（autonomous 預設，記於此）

1. **儲存**：Option 2 — 沿用現有共用表，不加 market 欄、不動 PK。upsert 寫 `exchange=TWSE`/`currency=TWD` 自描述。（可逆、非 hack：discriminator 已存在於 exchange/currency。）
2. **上庫範圍（3081 MVP）**：company + facts（三表 as-reported，含台股 NCI/legal_reserve 家族）+ derive-base(metrics) + derive-analytics(metrics/RATIO)。**不含** dimensional（台股無 segment 揭露）、不含 nongaap（台股無 8-K 對等）。
3. **前端幣別**：資料驅動。formatter 讀 cell `unit` 前綴決定貨幣符號（USD→隱含 $/statements 裸數字；TWD→per-share/ratio 需 NT$，money statements 沿用裸數字＋表頭標幣別）。不硬編。
4. **ticker discovery**：新增 `/api/financials/companies`（DB 查 companies 表回 `{ticker,name,exchange}`），picker 動態＋依 exchange 分組（US / 台股）。避免每加 ticker 改 code。（比硬編 list 乾淨，符合「考慮後續擴展」。）
5. **前端 3 條台股列**：BS_ROWS 加 `legal_reserve`/`minority_interest_bs`/`total_equity_incl_nci`（收斂 compose-financials 已先行的 frontend-parity delta）。US 不受影響（這些 key US 資料不存在 → 該列自然空/隱藏）。
6. **NLM 核對即 Phase D**：`parse-tw-crosscheck` live 逐期跑，tol=0，0 MISMATCH（或已解釋）才准上庫 = 也就是 goal 的「跟 NLM 核對每個數字」。

---

## 2. 里程碑與依賴

```
M1 聯亞 3081
  D1 NLM cross-check(17 期) ──gate──┐
  E1 upsert_twse(TDD)→dry-run──────┼─→ E1-apply(USER AUTH) ─→ E3 前端渲染+對NLM驗收
  E2 前端 TWD(TDD, 與 D1/E1 平行) ──┘
M2 台達電 2308（M1 過才做）
  P 補 parse 缺期 → derive → D crosscheck → E upsert(auth) → 前端 → NLM 驗收
```

- E1(upsert 腳本) 與 E2(前端 code) 不依賴實際數值 → 可與 D1 平行建。
- E1-apply、E3-verify 依賴 D1 通過（值確定）+ E1-apply（資料入庫）。

---

## 3. 各 Track 契約

### D1 — NLM cross-check 3081（I drive）
- 逐期 `notebook_query(source_ids=[該期 Separate PDF])` 要三表逐列 `{label,value,unit,statement}`。
- 存 `raw_nlm_responses_twse/{period}.json` → 跑 `cross_check_twse.py` → `{3081}_twse_cross_check.md`。
- 收斂：0 MISMATCH、0 UNMAPPED（或補 label_to_key / 解釋）。MISMATCH 若為 parse 抽錯 → 修 parse-twse-ixbrl（慎重，走 Argue）。
- 17 期成本高 → 可先跑代表期（每年各季 + 年報）驗 pipeline，再全量。

### E1 — `scripts/upsert_twse_financials.py`（subagent, TDD）
- Mirror SEC upsert 的 dry-run/`--apply`/freshness-gate/snapshot-replace 機制。
- 差異：MOPS Filings 路徑；load twse_facts + derive-base + derive-analytics；`adapt_company_twse`/`adapt_twse_facts`；無 nongaap/supplement/edges。
- facts-wins guard、derive rule_id scoped snapshot 沿用。
- 驗收：dry-run 3081 → 0 rejected、coverage 合理、freshness 綠；**不 apply（等 auth）**。

### E2 — 前端 TWD（subagent, TDD, vitest）
- `statementFormat.ts`：MONEY_UNITS += `TWD_millions`/`TWD_thousands`；per-share 加 `TWD_per_share`。
- `constants.ts` `fmtValue`：加 TWD_* 分支（per-share → `NT$`；money → 同 US 裸數字邏輯）。
- `constants.ts` BS_ROWS：加 3 列（位置：`legal_reserve` 於 retained_earnings 後；`minority_interest_bs`/`total_equity_incl_nci` 於 total_equity 後、total_liabilities_and_equity 前）。ROWS_BY_STATEMENT 同步。
- 更新 `tests/test_frontend_parity.py`（compose 端）預期：delta 收斂為 0。
- ticker discovery：`/api/financials/companies` route + picker 動態化。
- 驗收：vitest + tsc 綠；美股渲染零回歸。

### E3 — 渲染 + NLM 驗收（I drive, preview tools）
- dev server 起，開 `/financials/3081`，逐表對 NLM 值 + DB 值三方一致。

---

## 4. 驗證紀律（承前教訓）

- subagent 全 Opus 4.8（[[feedback_subagent_model_opus]]）。
- **controller 親自複跑所有 gate**（dry-run/測試/diff），不採信 subagent 的 gate 宣稱（前有造假前例）。
- production write（`--apply`）逐次出 dry-run diff → 明確 user 授權才 apply。
- 美股零回歸：E2 前端改動後美股 5 ticker 頁面值不變。

## 4b. M1 聯亞 3081 執行結果（2026-07-05 完成）

- **Phase D**：對當前 canonical facts 重跑 crosscheck = 906 MATCH / 25 MISMATCH（全 NLM 端）/ 1 NLM_ONLY / 3 UNMAPPED。零真實 parse 錯。2 大類（capex Q1_FY2024、other_payables）已對原始 iXBRL 源頭裁決 parse 全對。checker 補 report_category-aware 修正（ir filer code 8200→net_income，derive-A rename 引入的迴歸；11 期驗 net_income==NLM 8200）。
- **E1 上庫**：3081 進 production（2101 facts + 349 derive-base + 874 analytics + 1 company）。user 授權。
- **E1 修 bug（重要）**：原 upsert 用 `adapt_twse_facts`（derive adapter：capex 翻正、排除現金餘額）寫 facts → **錯**。改用新 `adapt_twse_canonical_facts`（as-reported：capex 帶負號、保留 beginning/ending_cash），facts 2043→2101。re-apply 驗 DB capex=-42553、cash present、無孤兒。
- **E2 前端**：TWD formatter + 3 台股權益列 + ticker discovery + **As-Reported 預設修正**（TW 無 presentation-linkbase display metadata → As-Reported 空表；新增 `hasAsReportedLayout` data-driven 判斷，無 metadata 時強制 Standardized + 隱藏 toggle）。美股零回歸（INTC As-Reported 正常）。90+4 vitest + tsc 綠。
- **E3 驗收**：/financials/3081 預設即渲染（IS 30 列 / BS 38 / CF 22 / Ratios 32），值全對 NLM（Revenue 904389、Net Income 317515、EPS 3.44/3.43、Gross Margin 54.8%…），capex 顯示 (42,553) 負號、Ending Cash 762,414。NCI 條件列對 ir filer 正確隱藏。

### 已知待辦（M1 deferred，非 correctness）
- **total_liabilities_and_equity 缺**：parse-twse-ixbrl 未 map `ifrs-full:EquityAndLiabilities` → BS「負債及權益總計」列空白（值 = total_assets 5,678,137，已由 total_liabilities+total_equity 三列呈現）。需 parse 加 mapping + re-parse + re-derive + re-upsert（parse 改動，慎重）。2308 同缺，宜一次修。
- **pre-FY2022 期無 NLM 核對**：notebook 只有 FY22Q1–FY26Q1 MOPS PDF；更早期 parse facts 存在（footing 過）但無第二來源。要驗需先補 PDF sources。
- 前端 ratio label「non-GAAP」上標對台股 IFRS 略不精確（cosmetic）。

## 5. M2 台達電 2308 執行結果（2026-07-05 完成）

2308 是 **cr（合併報表）** filer，NCI 家族有值（對照 3081 ir 隱藏）。memory 說「剩 16 期未跑」已過時 —— parse 21 期（Q1_FY2021–Q1_FY2026）早已備妥、21 raw iXBRL 齊。

- **derive**：新共用引擎 `--market tw` 跑 derive-base 301 + derive-analytics 670（全套 34 ratio rule）。
- **Phase D NLM 核對**：**871 MATCH / 0 MISMATCH / 0 NLM_ONLY / 0 UNMAPPED**，20/21 期，tol=0，完美對帳。cr NCI 家族（8200/8610/8620）全對。NLM 讀值 = 既有 5 期 + 本次 subagent 收集 15 期（Opus，我 deterministic 複跑 cross_check 驗證，非採信）。**Q3_FY2023 未驗**：NLM source `04454d89` 伺服器端損壞（INVALID_ARGUMENT，含 source_describe，auth refresh 無效）→ 需 NotebookLM 重新上傳該 source 後補跑。Q4_FY2021 首讀有漏/誤，subagent targeted re-query 修正後 44 MATCH。
- **upsert**：2308 上 production（2021 as-reported facts + 301 + 670 metrics）。user 授權。dry-run clean、NCI 對帳完美。
- **frontend 驗收**：/financials/2308 渲染 IS 30 / BS 38，**NCI 條件列有值**（Net Income pre-NCI 23,834,549 / NCI 3,278,958 / Net Income 20,555,591，相加對；BS 非控制權益 57,716,461 / 權益總額含NCI 357,259,207 / legal_reserve 42,601,564），值全對 NLM。市場條件列設計在真資料端到端驗證：cr 顯示、ir 隱藏。

**Phase E 兩 ticker 全線完成。**

## 6. Deferred 三項處置定案（2026-07-05）

- **#1 total_liabilities_and_equity — ✅ 修好**：parse-twse-ixbrl `XBRL_MAP` 加 `ifrs-full:EquityAndLiabilities → total_liabilities_and_equity`（BS, sort 3990；TDD）。re-parse 3081+2308（純加一列/期，其餘零變動，值=total_assets，footing 不受影響、crosscheck 906/915 不變）→ re-derive → re-upsert（3081 2101→2130 facts、2308 2021→2042）。前端兩檔 BS「Total Liabilities & Equity」列現在有值。
- **#2 2308 Q3_FY2023 — ✅ 補齊**：原 NLM source `04454d89` 伺服器端損壞；本地 PDF 重新上傳成新 source `d8e71f16`（config 已更新），該期補驗 44 MATCH → **2308 21/21 全綠（915 MATCH）**。
- **#3 3081 pre-FY2022 — ✅ 定案為 parse-only（user 拍板）**：聯亞 notebook 只有 FY22Q1+ PDF，pre-FY2022（FY2019–2021）無 NLM 來源檔;`fetch_ixbrl.py` 只抓 iXBRL XML 抓不到財報 PDF，補驗需另寫 MOPS PDF 下載器抓 12 季老 PDF，對舊資料投入不成比例。**維持 footing-validated parse-only**（內部恆等式已驗，僅缺第二來源），記為 inherent limitation。
