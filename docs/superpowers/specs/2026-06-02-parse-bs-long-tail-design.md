# Design Spec：parse-10QK-gaap BS long-tail catch-all（+ 同義 tag 補核心）

Date: 2026-06-02 / Project: ai_agent / Skill: `parse-10QK-gaap`
Status: **DRAFT v3，Codex round-2 = conditional pass（2 P2 + 1 P3 全折回，見 §14）**，待人類核可即可進 Build（未動 code）
作者交接：跨 ticker BS footing 稽核工單 `tmp/parse-bs-footing-audit-worklist.md` 的正式設計解。

---

## 0. TL;DR

跨 ticker 稽核發現 BS footing 缺口（LITE 18 期、MU 16 期、INTC/SNDK 數期），根因是**未映射的標準 us-gaap BS tag 被直接丟掉**。架構文件早就規定「不在 90 個核心 uni_account 的科目要進該 section 的 long-tail bucket」，但 **extractor 從沒實作 BS 的 long-tail 路由**（只實作了 IS/CF 的 composite-fallback）。本 spec 把這個缺的機制補上，**不新增核心 key、不違反 uni_account 紀律**。

關鍵 de-risk：**前端 5 個 BS bucket 早已定義**（`constants.ts` + matrix builder/渲染/weight 通用）→ 主體是 **parser-side**，前端只需**一處小修**（§5b：suppression 語意）。

⚠️ **Phase 0 前置（Codex round-1 P1，硬擋）**：`full_linkbase.py` 的 cal period label 是**月曆推導、非 fiscal-aware**，對非 12 月結的 ticker（MU fy-end=8、LITE、SNDK fy-end=6）會把 cal edge 掛到**錯的 fiscal 期**，導致 cal↔facts period 對不上（實測 MU：facts 有 `Q2_FY2026`+全部 Q3，cal 沒有；cal 有 `FY20xx`，facts 用 `Q4_FYxxxx`）。**這也使本工單稽核對 MU/LITE/SNDK 的 per-period footing 數字不可靠**（A/B tag 識別仍指示性正確，但期數/per-period diff 要修完 period mapping 後重抽）。**修 period mapping = MU 當 Phase-1 gate 的前置**。

---

## 1. 為什麼做（problem）

- `BS_TAG_MAP`(+ ticker override) + label-discovery 兩條路都沒命中的 us-gaap BS tag → **不 emit、直接丟掉**（不是進 bucket）。
- 後果：① BS 表面對不平 ② 個別科目行漏抓/低估（如 MU PP&E 只剩 net-only，少掉合併行 ~$48B 量級）。
- ratio 安全（用官方揭露的 `AssetsCurrent`/`LiabilitiesCurrent` 小計），但 BS 顯示與科目完整度受損。
- 完整逐 tag/期數/金額清單見 `tmp/parse-bs-footing-audit-worklist.md`；重現 `tmp/parse-bs-footing-audit.py`。

## 2. 原則錨點（不可違反）

LOCKED `docs/financials-core-checklist.md`（v5，90 核心 uni_account）+ `docs/financials-architecture.md`：

- `uni_account` 只能是 **90 個核心 universal key** 或 **12 個 long-tail bucket**（含 `misc_long_tail`）。**禁止自由創造新 uni_account。**
- 不在核心字典的科目 → 該 section 的 long-tail bucket，帶 `weight` + `rolls_up_to`。
- long-tail → core 的「升級」只能走 checklist 登記流程（登記 + 勾 ✅ + 加 TAG_MAP + 重抽歷史），**不在本案 ad hoc 做**。
- 三層用 key：Statement view 用 `source_account`（全顯示）；Comparison view / 分析層用 `uni_account`（核心 + bucket 與核心 other 加總）。

## 3. 架構現況（已查證）

| 元件 | 現況 | 對本案的意義 |
|---|---|---|
| 前端 5 BS bucket | `constants.ts` 已定義 `current_asset_long_tail` / `noncurrent_asset_long_tail` / `current_liability_long_tail` / `noncurrent_liability_long_tail` / `equity_long_tail`，`kind:"long_tail_bucket"`，已在 `BS_ROWS` | **不用改前端渲染**；buckets 自動出現在對的 BS 區塊 |
| 前端聚合 | `useFinancialMatrix.ts` 對所有 bucket 通用：用 `long_tail_metadata.rolls_up_to`（優先）或 `LONG_TAIL_ROLLUP_HINTS[xbrl_tag]` 偵測 + 抑制 double-display；`weight` 參與加總 | 只在「合併 vs 拆開並存」時需補 `LONG_TAIL_ROLLUP_HINTS` 條目 |
| extractor `xbrl_extract.py` | 只吃 companyfacts，**無 cal linkbase**；long_tail 只做 IS/CF composite-fallback | BS section 路由不適合放這裡（沒有父子結構） |
| `build_separated.py` | 第 2 步 fetch cal/pre/lab linkbase；讀 inline gaap.json + raw cache；產 facts.json + 注入 long-tail roll-up edges | **cal 父小計 + raw 值都在這層** → BS long-tail 偵測的正確落點 |
| `{ticker}_xbrl_raw.json` | companyfacts 原始 cache（us-gaap 值可查） | 未映射 us-gaap tag 的值來源 |

## 4. 稽核發現的三類（決定每個 tag 走核心 vs bucket）

| 子類 | 判準 | 處置 | 代表 tag |
|---|---|---|---|
| **① 通用科目的同義/別名 tag** | 語意 = 90 核心之一，只是公司換 tag 報 | 加 candidate 到**既有**核心 key（first-match-wins，拆開版優先）| `TreasuryStockCommonValue`→`treasury_stock`；`AvailableForSaleSecuritiesDebtSecuritiesNoncurrent`→`long_term_investments`；`PropertyPlantAndEquipmentAndFinanceLeaseRightOfUseAsset…`→`ppe_net`（見 §6 註）|
| **② 無核心歸屬的特殊項目** | 不對應任何核心 key | 進對應 **BS long-tail bucket**（§5）| `EmployeeRelatedLiabilitiesCurrent`、`ConvertibleDebt(Non)Current`、`GovernmentAssistanceLiabilityNoncurrent`(CHIPS)、`IncomeTaxesReceivable(Noncurrent)` |
| **③ 跨多核心 key 的合併 tag** | 一個 tag = 多個核心科目合併 | 逐筆裁決（§6）：映主核心 key、或當 bucket 合併行 | `DebtCurrent`、`LongTermDebtAndCapitalLeaseObligations`、`CommonStocksIncludingAdditionalPaidInCapital`、`StockholdersEquityIncludingPortionAttributableToNCI` |
| **B（非本案）** | 公司自訂 extension tag | companyfacts 無值 → 維持 Known Limitation | `mu:*`、`intc:*`、`sndk:*` |
| **排除** | 註腳/fair-value disclosure 非 BS face | 不映射 | `CashAndCashEquivalentsFairValueDisclosure` |

## 5. 設計主體 — BS long-tail catch-all（② 類，核心交付）

**落點**：`build_separated.py` 新增一步（cal fetch 之後、寫 facts.json 之前）。理由見 §3。

**演算法（deterministic，無 LLM）**：

0. **先選定 face-BS role**（Codex round-1 P2-role）：`full_linkbase.py` 的 `_dedup` 不含 `role_uri`，但 cal edge 仍帶 role_uri，且 `cal_sum_sanity.py` 按 (period, axis, **role_uri**, parent) 分組（同 parent-child 跨 role 出現會雙計）。leaf 偵測**必須 role-scoped**：先選定 face-of-BS role（role_uri 含 `BALANCESHEET` / `StatementOfFinancialPosition` 類），只在該 role 內做 §1-2，不混 footnote/detail role。
1. 在 face-BS role 內，取所有 `parent_qname` ∈ {`Assets`,`AssetsCurrent`,`Liabilities`,`LiabilitiesCurrent`,`StockholdersEquity`,`LiabilitiesAndStockholdersEquity`} 的 edge。
2. 對每個 (period, child)：若 child 的 local tag **未**被 emit 成核心 fact（不在該期 captured 核心 source_account 集合），且 child 是 **us-gaap namespace**，且該 child 在**該 face-BS role 內**相對此 subtotal 是 **leaf**（不是其他已 captured child 的父，避免父子雙計）→ 視為未映射子科目。
3. 從 `{ticker}_xbrl_raw.json` 用 child tag + period_end 查值；查不到（extension tag / 無值）→ 不 emit，但**寫進一級 anomaly report**（見 §5c），不靜默跳過。
4. emit long-tail fact：

   | 欄位 | 值 |
   |---|---|
   | `uni_account` | cal 父小計 → bucket（見對照表）|
   | `source_account` | 原 us-gaap tag |
   | `value` | raw companyfacts 值 |
   | `weight` | cal edge weight（±1）|
   | `statement` | `BS` |
   | `unit` | 同 ticker scale |
   | `long_tail_metadata.rolls_up_to` | 父小計的核心 uni_account |
   | `long_tail_metadata.is_recurring` / `last_occurrence_date` | 由跨期出現情況計 |

5. 把 rolls_up_to 注入 cal roll-up edges（沿用既有 §3 機制）—— **但這是補充結構資料，不可取代 facts metadata（見下）**。

**facts.json metadata 保留契約（Codex round-2 P2-b，Build requirement）**：BS long-tail fact 的 `long_tail_metadata`（含 `rolls_up_to`）**必須保留在 `{ticker}_gaap_facts.json` 的該 row 上**。現行 `build_separated.py:67` 會把 inline rows 的 `long_tail_metadata` **strip 掉只轉成 cal edge**，但 upsert 管道的 adapter（`sec_json_adapter.py:448 adapt_gaap_facts`）是**從 facts.json 讀 `long_tail_metadata`**，cal edge 不參與 Viewer 顯示/聚合。→ 對 BS long-tail rows **不可 strip**；否則進 Supabase 的 `long_tail_metadata=None`，前端 §5b 的 kind-aware suppression / bucket rolls_up_to 結構聚合全失效（現有 IS/CF long-tail 是靠 `LONG_TAIL_ROLLUP_HINTS` xbrl_tag 撐 suppression，BS 這些 tag 不在 hints map，沒有 fallback）。

**父小計 → bucket / rolls_up_to 對照**：

| cal parent | bucket uni_account | rolls_up_to |
|---|---|---|
| `AssetsCurrent` | `current_asset_long_tail` | `total_current_assets` |
| `Assets`（非同時掛 AssetsCurrent）| `noncurrent_asset_long_tail` | `total_assets` |
| `LiabilitiesCurrent` | `current_liability_long_tail` | `total_current_liabilities` |
| `Liabilities`（非同時掛 LiabilitiesCurrent）| `noncurrent_liability_long_tail` | `total_liabilities` |
| `StockholdersEquity` | `equity_long_tail` | `total_equity` |
| `LiabilitiesAndStockholdersEquity`（直掛，罕見）| 依子科目性質落 equity 或 misc（open Q5）| — |

**double-count 防護**：
- 只 emit「未被任何核心 fact captured」且「相對該 subtotal 為 leaf」的 child（步驟 2）。
- 同一 child 同時掛多個 subtotal（current + total）時，**只算最內層**（current），避免重複。
- 若某 ① 類同義 tag 已映進核心，其值不會再被 long-tail 撈（已 captured）。
- 合併 vs 拆開並存（③ 類映核心後）若仍有殘留拆開子被 cal 掛在 subtotal → 補 `LONG_TAIL_ROLLUP_HINTS` 抑制前端雙顯。

## 5c. 防禦式設計：anomaly report（不 silent-drop）（NLM round-1）

每次 build 產一份 `{ticker}_bs_footing_anomalies.json`，列出每個 BS 小計每期的：未映射子科目（A 類 us-gaap、companyfacts 有值 → 已進 bucket）、**拿不到值的子科目**（B 類 extension / companyfacts 無值 → 列報、未 emit）、**cal 缺失/異常**（該期無 face-BS role、cyclic、role 模糊）。原則（NLM「不能 silent-drop」）：**寧可吵、不可悄悄丟**。cal_sum_sanity 既有 "partial" 是軟訊號，這份是把 BS 的漏抓/拿不到/cal 異常變成可審的一級輸出。

## 5b. 前端 suppression 語意修正（Codex round-1 P1，必改）

**問題（已驗證 `useFinancialMatrix.ts:214-227`）**：long-tail child 的 suppression 判準是 `long_tail_metadata.rolls_up_to`（優先）或 `LONG_TAIL_ROLLUP_HINTS[xbrl_tag]`，**只要 target cell 已 populated 就抑制該 child**。本案 BS bucket 的 `rolls_up_to` = subtotal（`total_current_assets` 等），而 BS subtotal **永遠 populated** → **所有 BS long-tail child 被抑制 → bucket 永遠顯示 "—"（空）**。

**修法（採 kind-aware guard，非 Codex 建議的 hints-only）**：suppression **只在 target row `kind === "core"` 時觸發**，subtotal target 不抑制。
- 理由：`rolls_up_to` 指向 subtotal 是**結構性 roll-up**（footing/comparison 用），不是「核心已重複」訊號；只有指向**核心 item**（如 SG&A composite → `selling_general_administrative`、D&A composite → `depreciation_and_amortization`）才是真 double-display。
- **比 hints-only 低風險**：hints-only 需把現有靠 `metadata.rolls_up_to` 抑制的 case（INTC/LITE 的 D&A composite，target 是核心 item，**目前不在 `LONG_TAIL_ROLLUP_HINTS`**）全部遷進 hints map，否則 D&A 會 regress 成雙顯。kind-aware 保留兩條路徑、只排除 subtotal，零遷移、零 regression。
- 實作：rows 已帶 `kind`；建 `kindByKey`，line 220 加判 `kindByKey[hintTarget] === "core"` 才進 suppress。
- 驗證：既有 AAOI SG&A / INTC・LITE D&A 抑制行為不變（target 皆 core）；BS bucket（target subtotal）正常渲染。納入前端 regression。

## 6. ① 類同義 tag 補核心 + ③ 類逐筆裁決

**① 類（加 candidate 到既有核心 key，`bs_tag_map_for_ticker` / 全域 BS_TAG_MAP first-match-wins，拆開版優先）**：

| 核心 key | 補的 candidate tag | 證據要求 |
|---|---|---|
| `property_plant_equipment_net` | `PropertyPlantAndEquipmentAndFinanceLeaseRightOfUseAssetAfterAccumulatedDepreciationAndAmortization` | 註：此 tag 含 finance-lease ROU；須確認與 `operating_lease_rou_asset`(`right_of_use_assets`) **不重疊**（operating vs finance lease）+ footing diff=0 |
| `treasury_stock` | `TreasuryStockCommonValue` | source-faithful + footing |
| `long_term_investments` | `AvailableForSaleSecuritiesDebtSecuritiesNoncurrent` | source-faithful + footing |

> 原則辯護：① 類**不是新 uni_account**，是把「公司用不同 tag 報的同一個核心科目」對到既有核心 key——與已核可的 MU 應收（`ReceivablesNetCurrent`→`accounts_receivable`）、LITE ASC606（`ContractWithCustomerAssetNet`→`accounts_receivable`）同性質。全域 vs ticker-override 依跨 ticker first-match 安全性逐 tag 定（走 LITE/MU 等價驗證紀律）。

**③ 類逐筆裁決（合併 tag）**：先傾向**當 bucket 合併行**（保 source-faithful、不硬拆），除非該合併恰好等於單一核心 key：

| tag | 傾向 | 理由 |
|---|---|---|
| `DebtCurrent` | bucket（`current_liability_long_tail`）or 映 `short_term_borrowings`？| MU 不報拆開版；但語意是「當期到期債務合計」跨 ST/current-LTD。Open Q3 |
| `LongTermDebtAndCapitalLeaseObligations` | 映 `long_term_debt`？or bucket | 合併 LTD + capital lease，兩者皆核心。Open Q3 |
| `CommonStocksIncludingAdditionalPaidInCapital` | bucket（`equity_long_tail`）| 合併 common_stock + APIC 兩核心，硬拆無據 |
| `StockholdersEquityIncludingPortionAttributableToNCI` | 不映（= 含 NCI 的權益總，屬 subtotal 層，靠 `total_equity` + `minority_interest_bs`）| 避免與 `total_equity` 衝突 |

## 7. 不改 / 不碰

- **核心 90 key 不動**（LOCKED）；本案零新核心 key。
- **前端**：渲染/聚合大致不動（5 BS bucket 已接好），**唯一例外是 §5b 的 suppression kind-aware 修正（必改）**；視情況補 `LONG_TAIL_ROLLUP_HINTS` 條目。
- **ratio / derive-analytics**：用官方揭露小計，不受影響。
- **B 類 extension tag**：companyfacts 拿不到值，維持 SKILL.md Known Limitation；要補值需另建 instance-XML 抽取能力（獨立大案）。

## 8. 驗證計畫

0. **Phase 0 前置必先過**（§13）：`full_linkbase.py` period mapping 改 fiscal-aware → MU cal↔facts period 100% 對齊（重跑稽核：facts BS 期 = cal BS 期，無孤兒期）。**未過不得開 Phase 1 gate。**
1. **MU 當第一驗證 ticker**（未進 production，安全）：
   - gate 改為（Codex round-1 P2-gate，避免與 B 類矛盾）：**A 類/companyfacts-addressable residual = 0；B 類 extension residual 明確列報、不計入 gate**（MU 仍有 `mu:AssetsHeldForSaleCurrent` 等 extension 缺口，companyfacts 拿不到值，永遠無法 diff=0）。
   - 斷言**零新核心 uni_account**（只核心 90 + 5 BS bucket）。
   - 零 double-count（face-BS role + leaf-only + captured 去重）。
   - cal sum sanity 0 ❌。
2. **已上線 ticker（INTC/SNDK/LITE）**：re-parse → 對先前 production 做 artifact diff。⚠️ **此類 bug-fix 改動預期 diff≠0**（NLM round-1：diff=0 等價驗證會把「漏抓」這個 bug 一起鎖死）——gate 不是「diff=0」，而是「**diff 恰好等於預期新增**（bucket 行 + ① 類核心補抓），且**零既有核心值被改動**」。逐家 re-upsert。
3. regression test：新增 `test_bs_long_tail.py`（bucket 路由、leaf-only、double-count 防護、① 類 first-match、跨 ticker 不誤映）。**外加 red-green edge-case 單元測試**（NLM round-1）：cal 缺該期 / cyclic / 無 face-BS role / role 模糊 → 走 fallback + 進 anomaly report，**不崩、不再次靜默丟**。
4. SKILL.md CHANGELOG + Known Limitations 更新（A 類那列從「待補」改為「已由 BS long-tail 解」）。

## 9. Open Questions（待 Codex / 用戶拍）

- ~~**Q1 落點**~~ → **Codex round-1 已確認 `build_separated.py` 可採**（前提：先修 period mapping + role-scope leaf + suppression）。
- ~~**Q2 inline 一致性**~~ → **Codex round-1 確認**：Phase 1 BS long-tail 只進 `facts.json` 可接受；但 **Phase 2 ① 類核心 tag 補抓仍須走 `xbrl_extract.py` / inline JSON**，讓 cross-check 對核心科目仍有意義。
- **Q3 ③ 類債務合併 tag**：映核心 vs 進 bucket（§6）。
- **Q4 ① 類全域 vs ticker-override**：逐 tag 跨 ticker first-match 安全性。
- **Q5** `LiabilitiesAndStockholdersEquity` 直掛子科目的歸 bucket 規則。
- **Q6 is_recurring / last_occurrence_date** 計法（跨期窗口）。

## 10. Rollout（分階段，每階段 Codex review）

0. **Phase 0（前置，硬擋）**：`full_linkbase.py` cal period mapping 改 fiscal-aware（§13）+ `cal_sum_sanity.py` period 對齊。驗：MU/LITE/SNDK cal↔facts period 100% 對齊。**完成後重抽稽核工單數字。**
1. **Phase 1**：build_separated BS long-tail catch-all（② 類，face-BS role + leaf）+ 前端 suppression kind-aware 修（§5b）+ MU 驗證（A 類 residual=0、B 類列報、零新核心 key）。
2. **Phase 2**：① 類同義 tag 補核心（PP&E/treasury/LT-inv，走 `xbrl_extract.py`/inline，保 cross-check）+ ③ 類裁決落地。
3. **Phase 3**：re-parse + re-upsert INTC/SNDK/LITE（已上線）+ 等價 diff。
4. 收尾：CHANGELOG / Known Limitations / `docs/financials-view-schema.md` 註記。

## 13. Phase 0 前置：full_linkbase period mapping 修 fiscal-aware

**根因**：`full_linkbase.py:226 derive_period_label(report_date, form)` 只用 report_date 的月曆月份推 fiscal quarter（`{3:1,6:2,9:3,12:4}` + 月份 fallback），不吃 `fy_end_month`。非 12 月結 ticker 整個位移（MU fy-end=8：真 Q3 5 月底→誤標 Q2、真 Q2 2 月底→誤標 Q1）。`xbrl_extract.py:195` 是 fiscal-aware 的，兩者標法不一致 → cal↔facts 對不上。

**修法方向（Codex round-2 P2-a：fiscal + axis + accession 三者都要釘死）**：
1. **fiscal-aware**：period label 用 `fy_end_month` 推（共用 xbrl_extract 同一套），不用月曆月份。**兩處 `derive_period_label` 都要改**：`full_linkbase.py:226` 與 `cal_sum_sanity.py:69`。
2. **axis-aware**：同一份 filing 內**依 axis 分派 period**——10-K 的 **BS（instant）edge → `Q4_FYyyyy`**（年末 snapshot），**IS/CF（duration）edge → `FYyyyy`**。不可像現在 `full_linkbase.py:268` 在解析 role/axis 前就對整份 filing 填單一 period。
3. **accession/context-aware raw lookup**：§5 raw 值查找用 **inline `filings[period].accession_number`（或 companyfacts `accn`）精準匹配**，不只 `tag + period_end`——同一 `period_end` 會跨多份 filing 出現（restatement），只靠 period_end 會抓錯期/錯版。

**驗收**：cal BS period 集合 == facts BS period 集合（無孤兒期），10-K 的 BS edge 落 `Q4_FYyyyy`、IS/CF edge 落 `FYyyyy`。⚠️ **修正先前措辭**：此改動會讓**所有 ticker**（含 12 月結）的 10-K BS cal edge 由 `FY`→`Q4_FY`（這是修正、非回歸）；真正「不變」的是 **facts.json 本體 byte-identical**（只 cal edge period 標籤變）+ IS/CF cal label。

**Phase 0 實作狀態（2026-06-03，已完成、待 Phase 3 per-ticker 重驗）**：✅ `fiscal_period_label` 落地（full_linkbase + build_separated `--fy-end-month` plumbing + cal_sum_sanity 對齊）；`test_period_mapping.py` 11 case 綠；**MU 端對端：cal BS 22 == facts BS 22（零孤兒）、cal sanity 0 ❌、facts.json 本體 byte-identical**。已上線 INTC/AAOI/SNDK/LITE 的 per-ticker 重抽+對齊驗證留待 Phase 3。accession-aware raw lookup 留待 Phase 1 build_separated。已同步 cc-switch(SSOT)+.claude+.codex+CC_Switch_Config 四 mirror。

## 14. Codex review log

### Round 1（2026-06-02）— 4 findings 全驗證屬實、全接受

| # | finding | 我的驗證 | 處置 |
|---|---|---|---|
| P1-frontend | BS long-tail 因 `rolls_up_to`=subtotal 被 suppression 濾掉、渲染空 | 確認 `useFinancialMatrix.ts:214-227`：target populated 即抑制，BS subtotal 永遠 populated | 接受。採 **kind-aware guard**（只 core target 抑制，subtotal 不抑制），比 Codex 的 hints-only 低 regression 風險，理由見 §5b |
| P1-period | `full_linkbase.py` period label 非 fiscal-aware，MU/LITE cal 掛錯期 | **實測 MU 確認**：facts 有 Q2_FY2026+全 Q3、cal 沒有；cal 有 FY20xx、facts 用 Q4。我的稽核 per-period 數字因此對 MU/LITE/SNDK 不可靠 | 接受。列為 **Phase 0 硬擋前置**（§13），修完重抽稽核 |
| P2-gate | footing diff=0 gate 與 B 類 extension out-of-scope 矛盾 | 確認 MU 有 `mu:` extension 缺口、companyfacts 拿不到值 | 接受。gate 改「A 類 residual=0；B 類明確列報、不計入」（§8） |
| P2-role | leaf 偵測未 role-aware；`_dedup` 不含 role_uri，sanity 卻按 role 分組 | 確認 `full_linkbase.py:342` dedup 無 role、`cal_sum_sanity.py:144` 按 role | 接受。leaf 偵測先選定 face-BS role 再做（§5 step 0） |

Codex review position：方向 OK、但修完 period mapping / suppression / gate 前不簽 implementation；Q2 facts.json-only 於 Phase 1 可接受，Phase 2 核心 tag 仍走 inline。→ 全數折回本 v2。

### NLM round（2026-06-02，notebook「Topic - Project Dev」d2973812）— 3 採納 / 2 不採納

| NLM 指出 | 評估 | 處置 |
|---|---|---|
| 靜默失敗：未映射 tag 直接丟 + cal linkbase 常不完整/錯誤，不可盡信（防禦式設計）| 高度相關，獨立佐證 Codex P1-period/P2-role | **採納** → §5c anomaly report（不 silent-drop）+ §5 step 0/3 cal 防禦 |
| diff=0 等價驗證鎖死現有 bug（Golden Master 盲點）| 犀利、正確；對「修漏抓」這種改動 diff=0 是錯的 gate | **採納** → §8.2 改「diff = 恰好預期新增、零既有核心值改動」+ §8.3 red-green edge-case 測試 |
| 90 核心 key 硬鎖 = 未來 IFRS 架構債 | 大致已解：台股走獨立 parse-twse-ixbrl 管道；dual-key ≈ Anti-Corruption Layer；misc_long_tail 是逃生口 | 不改架構，註記 |
| TLE / bitmask O(1) 階層儲存 | YAGNI：rolls_up_to 僅 1-2 層淺階層，Supabase+pagination 夠 | **不採納**（規模不符）|
| .cursorrules 約束 AI | 已做：CLAUDE.md/AGENTS.md 已寫死 schema 紀律 | 已涵蓋 |

### Round 2（2026-06-03）— conditional pass after P2 patch（2 P2 + 1 P3 全折回 v3）

無新 P1；round-1 四點 + NLM 三點確認實質折回。2 P2 + 1 P3：

| # | finding | 驗證 | 處置 |
|---|---|---|---|
| P2-a | period mapping 不夠釘死：要 fiscal **+ axis + accession**-aware（10-K 內 BS→Q4_FYyyyy、IS/CF→FYyyyy；`full_linkbase.py:268` 解析 axis 前就填單一 period；`cal_sum_sanity.py:69` 也月曆推導）| 確認屬實（= MU cal FY2020 vs facts Q4_FY2020）| 折回 §13（三者都釘 + 兩處 derive_period_label + raw lookup 用 accession）|
| P2-b | `long_tail_metadata` separated-facts 契約未修：`build_separated.py:67` strip 掉 metadata 只轉 cal edge，但 adapter `sec_json_adapter.py:448` 從 facts.json 讀 metadata、edge 不參與顯示 | 確認屬實（現有 IS/CF 靠 HINTS 撐，BS tag 無 hints fallback）| 折回 §5：facts.json BS long-tail rows **必須保留 long_tail_metadata**，cal edge 只補充 |
| P3 | §7 stale：仍寫「前端不改渲染/聚合」，與 §5b 矛盾 | 屬實 | 折回 §7 指向 §5b |

Sign-off：**conditional pass** — 補上 axis/accession mapping + long_tail_metadata preservation 契約（已折回 v3）後可進 Phase 0/1 Build。**Phase 2 的 Q3 債務合併 tag（③ 類）裁決仍須在動核心/analytics 前拍板**。本輪為 spec/ADR functional review，未跑測試。

## 11. 重現 / 測試

```bash
python3 tmp/parse-bs-footing-audit.py        # 稽核：footing 缺口 + A/B 分類 + 金額
# 實作後：re-parse MU → 重跑稽核應顯示 0 缺口（B 類除外）
```

## 12. 關聯

- 工單：`tmp/parse-bs-footing-audit-worklist.md`
- 原則：`docs/financials-core-checklist.md`（LOCKED v5）、`docs/financials-architecture.md`（long-tail bucket / Anchoring）
- 先例：SKILL.md CHANGELOG（MU 應收 prepend/suppress、LITE ASC606 override、CF D&A period-level composite）
- code：`xbrl_extract.py`（`BS_TAG_MAP` L473、`TICKER_BS_TAG_OVERRIDES` L556、`bs_tag_map_for_ticker` L565）、`build_separated.py`、前端 `app/components/financials-v2/{constants,useFinancialMatrix,StatementMatrix}.{ts,tsx}`
