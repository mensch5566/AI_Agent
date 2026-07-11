# parse-twse-ixbrl BS grouping 修正 — 2300/2399 殘差 + 股本三層 (spec v1)

> 2026-07-11。源自緯穎(6669)/健策(3653)21 期 NLM cross-check(statement-aware 修正後)發現的兩組 BS 對映問題。
> 鐵律:parse 只忠實讀 iXBRL tag、絕不運算;台美同語意 → 同 uni_account key。

## 0. 背景與證據

緯穎/健策 onboarding cross-check(tol=0)清掉工具端 CF-撞名假 mismatch 後,剩餘差異回溯到 **TWSE 標準表的三層 grouping 結構**,且經查**不是新 ticker 特例,是現有生產資料今天就存在的系統性問題**。

### 0.1 流動負債 grouping(代碼 2300 家族)

TWSE 標準表面板同時印三列(iXBRL 各自有 tag):

| 代碼 | tag | 語意 |
|---|---|---|
| 2300 | `ifrs-full:OtherCurrentLiabilities` | **grouping 小計** = 2320 + 2399 |
| 2320 | `tifrs-bsci-ci:LongtermLiabilitiesCurrentPortion` | 一年內到期長期負債 |
| 2399 | `tifrs-bsci-ci:OtherCurrentLiabilitiesOthers` | 其他流動負債－其他(**殘差**) |

**實測 2026Q1(TWD 仟元),四家 cr 全部 2300 = 2320 + 2399 精確成立:**

| ticker | 2300 寬 | 2320 | 2399 窄 | 現行 parse 雙計金額 |
|---|---|---|---|---|
| 緯穎 6669 | 3,173,625 | 2,224,488(公司債) | 949,137 | 2,224,488 |
| 台達電 2308 | 16,014,546 | 9,627,859 | 6,386,687 | **9,627,859(已上庫!)** |
| 台燿 6274 | 324,038 | 267,631 | 56,407 | **267,631(已上庫!)** |
| 健策 3653 | 22,269 | (無 2320) | 22,269 | 0(寬=窄) |

**現行 parse 同時 map 2300→`other_current_liabilities` 和 2320→`current_portion_of_long_term_debt`** → 2320 在 canonical 出現兩次。`total_current_liabilities` 等合計直接讀 as-reported 不受影響,derive 指標不受影響;錯在 BS 子科目層。舊 cross-check 為稀疏代碼抽查(~20 項)未覆蓋此列,故 6274/2308 歷史「全綠」不構成反證。

### 0.2 股本 grouping(代碼 3100 家族)

| 代碼 | tag | 健策 2023Q1 值 |
|---|---|---|
| 3110 | `tifrs-bsci-ci:OrdinaryShare` | 1,367,511(純普通股股本) |
| 3140 | `tifrs-bsci-ci:AdvanceReceiptsForShareCapital` | 13,361(預收股本) |
| 3100 | `ifrs-full:IssuedCapital` | 1,380,872(股本合計 = 3110+3140) |

現行 parse map 3100(小計)→`common_stock`。US GAAP 端 `common_stock` = par/ordinary(不含 stock subscribed)→ 台美同 key 不同語意。健策 cross-check 10 期 mismatch 即 NLM 讀 3110 窄列 vs parse 持 3100 小計。無 derive 指標消費 `common_stock`(BVPS/ROE 用 total_equity),故影響僅止顯示層與跨市場子科目可比性。

### 0.3 面板呈現差異(cross-check 端脈絡)

- 官方查核簽證版 PDF(緯穎/健策上傳):面板「其他流動負債」印**窄residual**,公司債另列 →「普通股股本」「預收股本」分列。
- iXBRL 標準表轉 PDF(台燿 29 期,headless Chrome 產):面板 2300/2399/3100/3110/3140 **全列都印**。
- 同一 label「其他流動負債」在兩種版式意義不同(殘差 vs 小計)→ cross-check label 對映必須能區分(見 §3)。

## 1. Change A — `other_current_liabilities` 改對映殘差(2399),小計 fallback

**Map 變更(`parse_ixbrl.py` XBRL_MAP,單一 skill 檔):**
- 主:`tifrs-bsci-ci:OtherCurrentLiabilitiesOthers`(2399)→ `other_current_liabilities`
- fallback:該期 instance **無 2399 tag 時**沿用 `ifrs-full:OtherCurrentLiabilities`(2300)→ `other_current_liabilities`(tag-presence 決定,無算術)。聯亞 3081(ir)即無 2399 → 行為不變。
- 2320 → `current_portion_of_long_term_debt` 不動。
- 2300 在有 2399 的 ticker **不再進 canonical**(grouping 小計,資訊 = 2320+2399,已被成分覆蓋)。

**理由:** (a) 消除 2320 雙計(緯穎 2.2B、台達電 9.6B、台燿 268M);(b) US 語意對齊 —— `us-gaap:OtherLiabilitiesCurrent` 即殘差,鐵律「同語意同 key」;(c) 仍是忠實讀 tag。

**已知限制:** fallback 到 2300 的 ticker(如聯亞)若某天出現 2320,殘差雙計會回來 —— 屬 tag-absence 驅動,記入 skill Known Limitations,cross-check 為偵測網。

## 2. Change B — 股本三層拆開(推薦 B-2,B-1 為替代)

**B-2(推薦,鐵律一致):**
- `tifrs-bsci-ci:OrdinaryShare`(3110)→ `common_stock`(對齊 US par/ordinary 語意)
- `tifrs-bsci-ci:AdvanceReceiptsForShareCapital`(3140)→ **新 TW 揭露 key `advance_stock_receipts`**(不跨市場比、無 derive 消費;walk view-schema 登記)
- `ifrs-full:IssuedCapital`(3100)不再進 canonical(= 3110+3140 小計);若 ticker 無 3110 tag 則 fallback 3100 → `common_stock`(同 §1 的 tag-presence fallback)。

**B-1(替代,現狀+透明化):** 3100 → `common_stock` 不動(TW 定義=含預收,schema 文件註明台美定義差),另抽 3140 → `advance_stock_receipts`。
- 使用者在發現 3110 tag 存在**之前**曾傾向 B-1;新證據(3110 純 tag 存在,B-2 亦為忠實讀 tag 且滿足鐵律)使本 spec 推薦 B-2。**最終由 argue + 使用者拍板。**

影響:B-2 會改 5 檔 TW ticker 的 `common_stock` 歷史值(僅預收股本非零的期別有差,多數期 3110==3100);derive 零影響。

## 3. Cross-check 端配套(parse-tw-crosscheck,非 parse)

1. **statement-aware compare 已上線**(本輪 TDD 完成,30 tests 綠):CF 撞名 BS 假 mismatch 已消(健策 221→70)。
2. `label_to_key` 增補:「其他流動負債－其他」→ `other_current_liabilities`;「預收股本」→ `advance_stock_receipts`;「股本合計」→(B-2 時)不對映或對 `issued_capital_total` 揭露 key(待 argue);「普通股股本」→ `common_stock`(B-2 下自然全綠)。
3. **小計列處理:** iXBRL 轉 PDF 版式會同時出現「其他流動負債」(2300 小計)與「其他流動負債－其他」(2399)。NLM label 帶代碼時以 code 優先對映(compare 核心已有 code_map 機制);純 label 撞名時,小計列進 expected-subtotal 忽略清單,不得靜默丟(記入 audit note)。
4. **NLM 端修復(與 parse 無關):** 健策 Q2_FY2022 整期 NLM 重抽(該期回應稀疏、值歪);其餘 ~30 個個位/十位小差(totals、OCR 類)逐筆翻 PDF 確認後標 NLM_ERROR 結案;緯穎 Q4_FY2021 operating_income 差 200、健策 Q4_FY2021 eps_diluted 9.41vs8.23、健策 dividends_paid ×5 一併查證。

## 4. 不變量

- 三表**合計**(total_assets/total_current_liabilities/total_equity/…)全部 as-reported 直讀,**改動前後 byte 不變**。
- parse 永不運算:兩處變更均為「換 map 的 tag / 新增 tag 對映 / tag-presence fallback」,無任何加減。
- IS / CF 全部不動;美股管道零觸碰。
- derive-base / derive-analytics 引擎零改動(無指標消費受影響 key;重跑僅因 facts 值變)。

## 5. Rollout

1. TDD 修 `parse_ixbrl.py`(canonical CC_Switch_Config,fixture 含:有 2399/無 2399、有 3110/無 3110、2300=2320+2399 樣本)→ sync-to-local。
2. 重 parse 5 檔 TW(6669/3653/6274/2308/3081)→ 重 derive-base/analytics。
3. 驗證:(a) 合計 byte-diff = 0;(b) 受影響子科目逐檔對 iXBRL 面板值;(c) 重跑 cross-check —— 預期緯穎 OCL×10、健策 common_stock×10 歸零。
4. NLM 端:健策 Q2_FY2022 重抽 + 小差 PDF 查證 → 兩檔 0 unexplained MISMATCH。
5. 生產:6274/2308(已上庫,值會變)+ 6669/3653(首上)逐檔**使用者授權** re-upsert;3081 若 fallback 無值變則免。
6. 文件:view-schema 登記 `advance_stock_receipts`(+`issued_capital_total` 若採)、common_stock 台美定義註記;skill.md CHANGELOG + Known Limitations;STATUS.md。

## 6. Out of scope

- 前端顯示層(新 key 的 row 顯示待後續)。
- 其他 grouping 家族全面掃描(2200/2219 其他應付款等 —— 本輪只修有 cross-check 證據的兩組;全面 grouping audit 另立工單)。
- 美股 parse 管道。

## 7. 風險

| 風險 | 緩解 |
|---|---|
| 2300=2320+2399 恆等式在其他期別/公司不成立(有未列成分) | fallback 規則不依賴恆等式;cross-check tol=0 逐期把關;fixture 納入台燿(有 2310 類成分?實測無)樣本 |
| B-2 改 common_stock 歷史值,下游(wiki 已 ingest 台燿 29 期)引用舊值 | 台燿 3110==3100(預收=0)→ 值不變;有變動之期別列清單供 wiki reconcile |
| 台達電 9.6B 子科目修正屬已上庫資料變更 | 逐檔授權 + upsert dry-run diff 先看 |
| 同 label 兩義(小計 vs 殘差)在 NLM 端誤對 | code 優先 + expected-subtotal 清單;audit 表逐筆可追 |
