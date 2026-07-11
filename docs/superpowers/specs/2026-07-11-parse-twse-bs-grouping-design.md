# parse-twse-ixbrl BS grouping 修正 — 2300/2399 殘差 + 股本三層 (spec v2, post-argue)

> 2026-07-11。源自緯穎(6669)/健策(3653)21 期 NLM cross-check(statement-aware 修正後)發現的兩組 BS 對映問題。
> 鐵律:parse 只忠實讀 iXBRL tag、絕不運算;台美同語意 → 同 uni_account key。
> **v2**:argue run `twse-bs-grouping`(architect×Opus vs skeptic,7 輪,consensus 17/17)收斂 —— **B-2 兩造一致採納**;9 個 DEFECT 摺入(fail-loud fallback、first-occurrence 實作機制、batch_parse 鏡像、CODE_TO_KEY 具體變更、wiki 重渲染、全史恆等式驗證、下游全量 diff、key 登記、issued_capital_total 拍板)。

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

## 1. Change A — `other_current_liabilities` 改對映殘差(2399),fail-loud fallback

**Map 變更(每個 active 鏡像,見 §5.0):**
- 主:`tifrs-bsci-ci:OtherCurrentLiabilitiesOthers`(2399)→ `other_current_liabilities`
- **fail-loud fallback(argue DEFECT 修正,取代 v1 的無條件 fallback):** 該期 instance 無 2399 時 —— 若 **2320 也不存在** → `ifrs-full:OtherCurrentLiabilities`(2300)→ `other_current_liabilities`(可證無雙計);若 **2320 存在** → **不對映**(OCL 留空)+ 寫 audit 警告(「2399 缺而 2320 在,broad fallback 會雙計」)。純 tag-presence 判斷,無算術。
- 2320 → `current_portion_of_long_term_debt` 不動。
- 2300 在有 2399 的期別**絕不**進 `other_current_liabilities`。

**實作機制(argue DEFECT:map-only 改法不可行):** `parse_ixbrl.py` 取值迴圈是 first-occurrence keep(`if metric_name not in results`,~L250),兩個 tag 都對映同 key 時勝者由文件順序決定 = 不可靠。必須改為**逐期收集候選 concept → 顯式 priority 選擇(2399 > 2300)→ fallback 條件檢查 → fail-loud audit**。守門檢查**只能比較、絕不輸出運算值**(禁止 emit 2300−2320 之類)。

**理由:** (a) 消除 2320 雙計(緯穎 2.2B、台達電 9.6B、台燿 268M);(b) US 語意對齊 —— `us-gaap:OtherLiabilitiesCurrent` 即殘差,鐵律「同語意同 key」;(c) 仍是忠實讀 tag。

**已知限制:** 2300 = 2320 + 2399 恆等式僅在抽樣期驗證;§5.3 對全史逐期驗證(比較性 gate,非輸出),不成立的期別進 audit 表(可能存在 2310 預收款項/2365 退款負債等未另抽成分 —— 該期 OCL 殘差仍正確,但 grouping 內未抽成分不在 canonical,屬既有 coverage 現狀,不劣化)。

## 2. Change B — 股本三層拆開(**B-2 已由 argue 兩造一致採納**,architect 0.90 / skeptic 0.95)

**B-2(採納):**
- `tifrs-bsci-ci:OrdinaryShare`(3110)→ `common_stock`(對齊 US par/ordinary 語意;cross-check `CODE_TO_KEY` 的 `3110→common_stock` 本來就是這個語意)
- `tifrs-bsci-ci:AdvanceReceiptsForShareCapital`(3140)→ **新 TW 揭露 key `advance_stock_receipts`**(不跨市場比、無 derive 消費)
- `ifrs-full:IssuedCapital`(3100)→ **新 TW 揭露 key `issued_capital_total`**(股本合計小計;argue 拍板:保留為揭露 key,不丟棄 —— 資訊不消失且 cross-check「股本合計」label 有明確去處)
- **fail-loud fallback:** 3110 缺時 —— 若 **3140 也缺** → 3100 → `common_stock`(可證 3100==純普通股);若 **3140 存在** → common_stock 留空 + audit 警告。無算術。

**B-1(未採納,留檔):** 3100 → common_stock 不動 + 註記。argue 裁決:B-1 違反「同語意同 key」鐵律(US common_stock 排除 stock subscribed);且 B-2 使健策 cross-check common_stock ×10 自然歸零。使用者先前傾向 B-1 是在 3110 tag 被發現之前。

影響:僅預收股本非零的期別 `common_stock` 值變(健策 1,380,872→1,367,511 + 新 `advance_stock_receipts` 13,361;台燿 29 期預收=0 → 值不變);`total_equity` 為獨立 as-reported tag,byte 不變;derive 零影響(無指標消費 common_stock)。有變動期別產清單供下游 reconcile。

## 3. Cross-check 端配套(parse-tw-crosscheck,非 parse)

1. **statement-aware compare 已上線**(本輪 TDD 完成,30 tests 綠):CF 撞名 BS 假 mismatch 已消(健策 221→70)。
2. **`CODE_TO_KEY` 具體變更(argue DEFECT:v1 只講 label 不夠):** `"2300"` 從 `other_current_liabilities` 改指小計去處(刪除或 `other_current_liabilities_subtotal` 忽略類);新增 `"2399"→other_current_liabilities`、`"3140"→advance_stock_receipts`、`"3100"→issued_capital_total`;`"3110"→common_stock` 不動(本來就對)。
3. `label_to_key` 增補:「其他流動負債－其他」→ `other_current_liabilities`;「預收股本」→ `advance_stock_receipts`;「股本合計」→ `issued_capital_total`(已拍板);「普通股股本」→ `common_stock`(B-2 下自然全綠)。
4. **同名兩義處理(小計 vs 殘差):** (a) 標準表轉 PDF:兩列都帶代碼 → code 優先解歧。(b) 查核簽證版(無代碼,如緯穎/健策上傳):面板「其他流動負債」**就是殘差**(公司債另列)→ label 對映 `other_current_liabilities` 直接正確;若某公司簽證版只印小計不印殘差 → parse 有 2399 值而 NLM 無對應列,compare 逐 NLM item 迭代天然不比對(非 mismatch),殘差列缺席記 coverage note,不得誤判。
5. **NLM 端修復(與 parse 無關):** 健策 Q2_FY2022 整期 NLM 重抽(該期回應稀疏、值歪);其餘 ~30 個個位/十位小差(totals、OCR 類)逐筆翻 PDF 確認後標 NLM_ERROR 結案;緯穎 Q4_FY2021 operating_income 差 200、健策 Q4_FY2021 eps_diluted 9.41vs8.23、健策 dividends_paid ×5 一併查證。

## 4. 不變量

- 三表**合計**(total_assets/total_current_liabilities/total_equity/…)全部 as-reported 直讀,**改動前後 byte 不變**。
- parse 永不運算:兩處變更均為「換 map 的 tag / 新增 tag 對映 / tag-presence fallback」,無任何加減。
- IS / CF 全部不動;美股管道零觸碰。
- derive-base / derive-analytics 引擎零改動(無指標消費受影響 key;重跑僅因 facts 值變)。

## 5. Rollout

0. **鏡像盤點(argue DEFECT):** 變更同步到每個 active 副本 —— canonical `~/CC_Switch_Config/skills/parse-twse-ixbrl/parse_ixbrl.py` + sync-to-local 鏡像,**以及 `~/AI_Agent/Tools/research-tools/parse-twse-ixbrl/batch_parse.py`(獨立老鏡像,同樣的舊 map,已驗證存在 L91/L103)**。
1. TDD 修 parse(priority 選擇機制 + fail-loud,fixture 含:有 2399/無 2399×有無 2320、有 3110/無 3110×有無 3140、2300=2320+2399 樣本、audit 警告路徑)→ sync-to-local。
2. 重 parse 5 檔 TW(6669/3653/6274/2308/3081)→ 重 derive-base/analytics。
3. 驗證 gates:(a) **合計 byte-diff = 0**(total_* 全部);(b) 受影響子科目逐檔對 iXBRL 面板值;(c) **全史恆等式驗證**:逐期比較 2300 vs 2320+2399、3100 vs 3110+3140(比較性檢查,不輸出運算值),不成立期別進 audit 表;(d) **derive 全量 diff**(argue RISK):比對重跑前後所有 derived 輸出(debt_to_equity/net_debt_to_ebitda/ROIC 等),證明無間接消費者意外變動;(e) 重跑 cross-check —— 預期緯穎 OCL×10、健策 common_stock×10 歸零。
4. NLM 端:健策 Q2_FY2022 重抽 + 小差 PDF 查證 → 兩檔 0 unexplained MISMATCH。
5. 生產:6274/2308(已上庫,值會變:台燿 OCL 268M→56M、台達電 OCL 9.6B 級修正)+ 6669/3653(首上)逐檔**使用者授權** re-upsert;3081 視 fallback 結果。
6. **Wiki 重渲染(argue DEFECT):** 台燿 29 期已進正式 Wiki 的 BS 頁面 OCL 值會變(324,038→56,407 級)→ 用 mops-10k deterministic renderer 的 update_page 能力對 29 期 re-render(股本不受影響,預收=0);知會 wiki session。
7. **Key 登記(argue DEFECT):** `advance_stock_receipts` + `issued_capital_total` 登記到 financials-view-schema、upsert display_label/ordinal map、cross-check CODE_TO_KEY/label_to_key、wiki-ingest-mops-10k Block C 契約;common_stock 台美定義註記。既有 viewer BS_ROWS 未顯示 OCL/CPLTD 屬既存顯示缺口,登記為 backlog 不擴本輪範圍。
8. 文件:skill.md CHANGELOG + Known Limitations(2300 恆等式期別 audit、fail-loud 條件);STATUS.md。

## 6. Out of scope

- 前端顯示層(新 key 的 row 顯示待後續)。
- 其他 grouping 家族全面掃描(2200/2219 其他應付款等 —— 本輪只修有 cross-check 證據的兩組;全面 grouping audit 另立工單)。
- 美股 parse 管道。

## 7. 風險

| 風險 | 緩解 |
|---|---|
| 2300=2320+2399 恆等式在其他期別/公司不成立(有 2310/2365 等未抽成分) | §5.3(c) 全史逐期比較性驗證 + audit 表;fail-loud fallback 不依賴恆等式;殘差對映本身仍正確 |
| fallback 在某 ticker「2399 缺 + 2320 在」→ OCL 留空 | 屬 fail-loud 設計本意(空 + audit 勝於雙計);cross-check NLM_ONLY 會標出 |
| B-2 改 common_stock 歷史值,下游引用舊值 | 台燿預收=0 → 值不變;變動期別清單供 reconcile;台燿 wiki 29 期因 OCL 仍須 re-render(§5.6) |
| 台達電 9.6B 子科目修正屬已上庫資料變更 | 逐檔授權 + upsert dry-run diff 先看 |
| 同 label 兩義(小計 vs 殘差)在 NLM 端誤對 | code 優先;查核簽證版無代碼時面板「其他流動負債」即殘差(§3.4);audit 表逐筆可追 |
| XBRL_MAP 第三欄(2195/3110 等)是顯示排序非代碼真值,易誤讀 | 文件註明;真代碼對映住在 cross-check CODE_TO_KEY 與 view-schema |
| 守門檢查被誤實作成輸出運算值 | spec 明文:比較可以、輸出禁止;TDD fixture 驗 audit 路徑不產生 facts row |
