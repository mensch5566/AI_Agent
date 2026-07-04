# compose-financials 台股支援(v2)Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 讓 render-only 的 `compose-financials` skill 用 `--market tw` 產出台股 ticker(聯亞3081/台達電2308)的 Financials.md,幣別/scale 資料驅動,三表 layout 台美共用,美股輸出僅 3 個預期 diff。

**Architecture:** compose 讀本地 JSON → ValueIndex → 依 CONTRACT 渲染三表+比率區塊 → AUTO-marker 幕等寫檔。台股:market-aware 路徑 + in-memory 把 `{T}_twse_facts.json`(keyed-dict)經 `_shared/twse_canonical_facts.emit_canonical_facts()` 攤成美股同 shape long-format;derive-base/analytics loader 不變(schema 已同)。幣別由每筆 `unit` 驅動;台股獨有列走條件渲染。

**Tech Stack:** Python 標準庫 + matplotlib(既有)、pytest。無新第三方依賴。

## Global Constraints

- **Canonical SSOT**:改 `~/CC_Switch_Config/skills/compose-financials/`,改完 `cd ~/CC_Switch_Config && bash scripts/sync-to-local.sh` 同步 4 mirror;`_shared/` 在 `~/AI_Agent/Tools/research-tools/_shared/`(已有 `twse_canonical_facts.py`)。
- **compose RENDER-ONLY**:只讀值、不算任何指標;缺指標 → 可見 placeholder。台股顯示 as-reported(capex 負、含 ending_cash),**不吃 derive_base 的翻正值進三表**。
- **美股零回歸**:INTC/MU/LITE/SNDK 的 Financials.md **只允許 3 種預期 diff**——frontmatter `updated:` 日期、FCF 列 `⏳→值`(§bug 修)、AAOI 另有 `$M→$K` 標籤。其他任何 diff = 回歸。**PNG 不入 byte gate**(matplotlib 非 byte-stable),改驗 md 圖檔引用 + 檔案存在。
- **顯示單位 = 申報單位**:不轉換 scale;formatter/title/chart 由每筆 `unit` 決定幣別符號($/NT$)與標籤($M/$K/NT$仟元)。
- **fail-closed**:未知 `--market` 由 argparse choices 擋;缺台股 facts → FileNotFoundError;glob 多命中 → fail-loud。
- **測試跑法**:`cd ~/CC_Switch_Config/skills/compose-financials && python3 -m pytest tests/ -q`(conftest.py 已把 `scripts/` 上 sys.path)。canonical 測完再 sync。
- **spec**:`docs/superpowers/specs/2026-07-03-compose-financials-tw-design.md`(v3.1,Opus+GPT-5.5 Argue 共識 + 批准)。

---

### Task 0: 美股回歸基準 + 比對腳本(改 code 前)

**Files:**
- Create: `$SCRATCH/compose_us_baseline/`(5 檔 Financials.md 複本)
- Create: `$SCRATCH/compose_regress.py`

**Interfaces:**
- Produces: `compose_regress.py <baseline_dir> <after_dir>` — 排除 frontmatter `updated:` 行後 diff 每檔;印每檔 PASS/DIFF + diff 行。Task 2/5/6 消費。

`$SCRATCH` = `/private/tmp/claude-501/-Users-mensch5566-AI-Agent/cec654d3-2750-4739-af9d-18d2863d7f2e/scratchpad`

- [ ] **Step 1: 跑 5 檔美股 compose 收基準**

```bash
SCRATCH=/private/tmp/claude-501/-Users-mensch5566-AI-Agent/cec654d3-2750-4739-af9d-18d2863d7f2e/scratchpad
mkdir -p "$SCRATCH/compose_us_baseline"
CF=~/CC_Switch_Config/skills/compose-financials/scripts/compose_financials/cli.py
for T in INTC MU LITE SNDK AAOI; do
  python3 "$CF" $T >/dev/null 2>&1 || python3 -m compose_financials.cli $T >/dev/null 2>&1
  cp ~/Obsidian/Khouse/Semiconductors/$T/03_Working/Topics/Trackers/Financials.md \
     "$SCRATCH/compose_us_baseline/${T}_Financials.md"
done
ls "$SCRATCH/compose_us_baseline"   # 應 5 檔
```

(若 `python3 cli.py` 因 relative import 失敗,用 `cd .../scripts && python3 -m compose_financials.cli $T`。)

- [ ] **Step 2: 寫 compose_regress.py**

```python
#!/usr/bin/env python3
"""US regression: diff compose Financials.md ignoring the volatile frontmatter `updated:` line."""
import sys, difflib
from pathlib import Path

def _norm(text: str) -> list[str]:
    return [l for l in text.splitlines() if not l.startswith("updated:")]

def main(baseline_dir: str, after_dir: str) -> int:
    fails = 0
    for bp in sorted(Path(baseline_dir).glob("*_Financials.md")):
        ap = Path(after_dir) / bp.name
        if not ap.exists():
            print(f"❌ missing after: {ap.name}"); fails += 1; continue
        a, b = _norm(bp.read_text()), _norm(ap.read_text())
        if a == b:
            print(f"✅ {bp.name}")
        else:
            print(f"❌ DIFF {bp.name}:")
            for line in difflib.unified_diff(a, b, lineterm="", n=0):
                if line.startswith(("+", "-")) and not line.startswith(("+++", "---")):
                    print("   " + line)
            fails += 1
    return 1 if fails else 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
```

- [ ] **Step 3: 自驗(基準對自己)**

Run: `python3 $SCRATCH/compose_regress.py $SCRATCH/compose_us_baseline $SCRATCH/compose_us_baseline`
Expected: 5 行 ✅,exit 0。(scratchpad 無 commit)

---

### Task 1: FCF contract-key 修正 + 死 key sweep 測試

**Files:**
- Modify: `~/CC_Switch_Config/skills/compose-financials/scripts/compose_financials/contract.py:90`
- Test: `~/CC_Switch_Config/skills/compose-financials/tests/test_contract_keys.py`(新)

**Interfaces:**
- Consumes: analytics emit 的 uni_account 集合(從 real 3081_analytics.json 取真值)。
- Produces: CF FCF 列 key = `free_cash_flow`;測試鎖住「CONTRACT 的 RATIO key 必須在 analytics 白名單或 §6 backlog 死 key 清單內」,防新增死 key。

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_contract_keys.py
"""Lock: every ('RATIO', key) in CONTRACT resolves to a real analytics uni_account,
except the known dead keys explicitly deferred in the spec §6 backlog. Prevents new
dead keys (the FCF-class bug found in Argue)."""
from compose_financials.contract import CONTRACT

# analytics-emitted RATIO uni_accounts (verified against real derive-analytics output)
ANALYTICS_UNIS = {
    "gross_margin_pct", "operating_margin_pct", "net_margin_pct", "effective_tax_rate",
    "current_ratio", "cash_ratio", "quick_ratio", "debt_to_equity", "interest_coverage",
    "free_cash_flow", "fcf_margin_pct", "ebitda", "ebitda_margin_pct",
    "adjusted_ebitda_margin_pct", "bvps", "roe", "roa", "asset_turnover",
    "dio", "dso", "dpo", "ccc", "roic", "net_debt_to_ebitda",
    "revenue_qoq", "gross_profit_qoq", "operating_income_qoq", "net_income_qoq",
    "eps_diluted_qoq", "revenue_yoy", "gross_profit_yoy", "operating_income_yoy",
    "net_income_yoy", "eps_diluted_yoy",
}
# Known dead keys deferred to spec §6 backlog (contract key != any emitter). Must NOT grow.
KNOWN_DEAD = {"fcf_margin", "nonoperating_income_expense_net", "net_working_capital",
              "capex_ratio", "cfo_to_net_income"}

def _ratio_keys():
    out = set()
    for sec in CONTRACT:
        for line in sec.get("lines", []):
            uni = line[1]
            if isinstance(uni, tuple) and uni[0] == "RATIO":
                out.add(uni[1])
    return out

def test_fcf_uses_free_cash_flow_not_fcf():
    assert "fcf" not in _ratio_keys(), "FCF contract key must be free_cash_flow, not fcf"
    assert "free_cash_flow" in _ratio_keys()

def test_no_new_dead_ratio_keys():
    dead = _ratio_keys() - ANALYTICS_UNIS
    assert dead <= KNOWN_DEAD, f"new dead RATIO keys (not in analytics, not in backlog): {dead - KNOWN_DEAD}"
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd ~/CC_Switch_Config/skills/compose-financials && python3 -m pytest tests/test_contract_keys.py -v`
Expected: `test_fcf_uses_free_cash_flow_not_fcf` FAIL(現 key 是 `fcf`)

- [ ] **Step 3: 改 contract.py:90**

```python
# 舊: ("**Free Cash Flow**", ("RATIO", "fcf"), M),
       ("**Free Cash Flow**", ("RATIO", "free_cash_flow"), M),
```

- [ ] **Step 4: 跑測試確認通過**

Run: `python3 -m pytest tests/test_contract_keys.py -v`
Expected: 2 PASS

- [ ] **Step 5: Commit**

```bash
cd ~/CC_Switch_Config && git add skills/compose-financials/scripts/compose_financials/contract.py skills/compose-financials/tests/test_contract_keys.py
git commit -m "fix(compose-financials): FCF contract key fcf->free_cash_flow + dead-key sweep test (Argue finding; US expected diff)"
```

---

### Task 2: 幣別/scale 資料驅動(fmt_value + title/ylabel + multi-unit fail-loud)

**Files:**
- Modify: `.../compose_financials/sections.py`(fmt_value + 新 helper + render 標題)
- Modify: `.../compose_financials/contract.py`(section title 拆 base + 移除硬編 `$M`;加 `money_fmt` 供 fail-loud 掃描不需,但標題改結構)
- Modify: `.../compose_financials/charts.py:56,64`(ylabel 參數化)
- Modify: `.../compose_financials/cli.py`(把 market/unit 尾綴傳入 render 與 chart)
- Test: `.../tests/test_currency_format.py`(新)

**Interfaces:**
- Consumes: 每筆 record 的 `unit`。
- Produces: `money_unit_label(unit) -> str`(`USD_millions`→`"$M"`、`USD_thousands`→`"$K"`、`TWD_thousands`→`"NT$ 仟元"`);`fmt_value` eps 分支依 unit 給 `$`/`NT$`;`render_section(..., regime, money_label)` 標題尾綴 = `（{regime}，{money_label}）`;三表區塊 multi-money-unit → `ValueError`。

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_currency_format.py
from compose_financials.sections import fmt_value, money_unit_label

def test_money_unit_label():
    assert money_unit_label("USD_millions") == "$M"
    assert money_unit_label("USD_thousands") == "$K"
    assert money_unit_label("TWD_thousands") == "NT$ 仟元"

def test_eps_currency_by_unit():
    assert fmt_value(1.23, "eps", "USD_per_share") == "$1.23"
    assert fmt_value(1.23, "eps", "TWD_per_share") == "NT$1.23"
    assert fmt_value(-1.23, "eps", "TWD_per_share") == "-NT$1.23"

def test_money_cell_unchanged():
    # 值不縮放、無幣別符號(幣別在標題),美股行為不變
    assert fmt_value(904389, "m", "TWD_thousands") == "904,389"
    assert fmt_value(12667, "m", "USD_millions") == "12,667"

def test_pct_unchanged():
    assert fmt_value(0.4215, "pct", "Pure") == "42.2%"
    assert fmt_value(42.15, "pct", "pct") == "42.2%"
```

- [ ] **Step 2: 跑確認失敗**

Run: `python3 -m pytest tests/test_currency_format.py -v`
Expected: FAIL(no `money_unit_label`;eps 未讀 unit)

- [ ] **Step 3: 實作 sections.py**

在 sections.py 頂部加 helper + 改 fmt_value eps 分支:

```python
_MONEY_UNIT_LABEL = {
    "USD_millions": "$M", "USD_thousands": "$K", "USD": "$",
    "TWD_thousands": "NT$ 仟元",
}

def money_unit_label(unit) -> str:
    """Money-scale label for section titles / chart y-axis, driven by the record unit."""
    return _MONEY_UNIT_LABEL.get(unit, "$M")

def _eps_symbol(unit) -> str:
    return "NT$" if unit and str(unit).startswith("TWD") else "$"
```

fmt_value eps 分支(line 30-31)改:

```python
    if fmt == "eps":
        sym = _eps_symbol(unit)
        return f"-{sym}{abs(v):.2f}" if v < 0 else f"{sym}{v:.2f}"
```

(m/sh/pct/x 分支不動。)

- [ ] **Step 4: render_section 標題尾綴 + multi-unit fail-loud**

`render_section` 簽名加 `regime="GAAP", money_label="$M"`;標題改由 base + 尾綴組。CONTRACT 標題先在 contract.py 拆掉硬編尾綴(見 Step 5)。render_section 開頭:

```python
def render_section(spec, idx, quarters, years, chart_md="", regime="GAAP", money_label="$M"):
    title = spec["title"]
    if spec.get("money_titled"):                      # 三表 + netsales 等帶幣別尾綴的區塊
        title = f"{title}（{regime}，{money_label}）"
    head = [f"## {title}", ""]
    ...
```

multi-unit fail-loud(只三表區塊,§3.2):在 render_section 迴圈後、組 body 前,對 `spec["statement"] in ("IS","BS","CF")` 的區塊,收集所有 `fmt=='m'` 且 resolve 到值的 row 的 unit,若 >1 種 money unit → raise:

```python
    if spec.get("statement") in ("IS", "BS", "CF"):
        money_units = set()
        for label, uni, fmt in spec["lines"]:
            if fmt != "m":
                continue
            for p in periods:
                u = _resolve_line(uni, spec.get("statement"), spec["version"], p, idx)[1]
                if u in _MONEY_UNIT_LABEL and u not in ("USD",):
                    money_units.add(u)
        if len(money_units) > 1:
            raise ValueError(f"section {spec['key']} mixes money units {money_units} — expected single filer scale")
```

- [ ] **Step 5: contract.py 標題拆尾綴 + money_titled 旗標**

把三表 + netsales-total 等硬編 `（GAAP，$M）`/`$M` 的標題**去掉尾綴**,改標 `"money_titled": True`。例:

```python
# is 區塊
{"key": "is", "title": "季度損益表 Income Statement", "money_titled": True, "grain": "quarter",
 "statement": "IS", "version": "GAAP", "chart": None, "lines": [ ... ]},
# bs / cf 同樣去尾綴 + money_titled
# netsales-total(line 114 "季度 Total Revenue（GAAP，$M）")→ 去尾綴 + money_titled
```

(EBITDA `$M`(line 149 附近若在標題)同樣處理;純 pct 區塊 margins/growth/returns 不加 money_titled。)

- [ ] **Step 6: charts.py ylabel 參數化**

```python
# line 37 balance_structure_chart 簽名加 ylabel="$M";line 56 用它:
def balance_structure_chart(labels, quick_assets, other_assets, liabilities, equity,
                            title: str, out_path, ylabel="$M"):
    ...
    ax.set_ylabel(ylabel)          # 原硬編 "$M"
# bar_chart 已有 ylabel 參數(line 64),呼叫端傳入即可。
```

- [ ] **Step 7: cli.py 把 regime/money_label 算好傳入**

在 `compose()` 迴圈(cli.py:102-110)為每個 spec 算 money_label + regime,傳給 render_section 與 chart:

```python
    market = ...   # Task 4 引入;本 task 先 default "us"
    regime = "IFRS" if market == "tw" else "GAAP"
    # money_label:取該區塊第一個 fmt=='m' 有值 row 的 unit;取不到 fallback 依 market
    def _section_money_label(spec):
        for label, uni, fmt in spec.get("lines", []):
            if fmt != "m":
                continue
            for p in q_window:
                u = idx.unit(uni[1] if isinstance(uni, tuple) else uni, p, spec["version"],
                             spec.get("statement", "IS"))
                if u in ("USD_millions","USD_thousands","TWD_thousands"):
                    return money_unit_label(u)
        return "NT$ 仟元" if market == "tw" else "$M"
    ...
    chart_md = _maybe_chart(spec, idx, q_window, assets_dir, ticker, money_label=_section_money_label(spec))
    body, placeholders = render_section(spec, idx, q_window, y_window, chart_md,
                                        regime=regime, money_label=_section_money_label(spec))
```

`_maybe_chart` 加 `money_label="$M"` 參數,傳給 `balance_structure_chart(..., ylabel=money_label)` 與 `bar_chart(..., ylabel=money_label)`。

- [ ] **Step 8: 跑 currency 測試 + 全套**

Run: `python3 -m pytest tests/ -q`
Expected: 新測試 PASS;既有測試全綠(標題結構改了,若 test_cli/test_sections 斷言舊標題字串需同步更新——更新為新 base title + 動態尾綴)。

- [ ] **Step 9: 美股回歸 gate**

```bash
mkdir -p "$SCRATCH/compose_us_after1"
for T in INTC MU LITE SNDK AAOI; do
  (cd ~/CC_Switch_Config/skills/compose-financials/scripts && python3 -m compose_financials.cli $T >/dev/null 2>&1)
  cp ~/Obsidian/Khouse/Semiconductors/$T/03_Working/Topics/Trackers/Financials.md "$SCRATCH/compose_us_after1/${T}_Financials.md"
done
python3 $SCRATCH/compose_regress.py $SCRATCH/compose_us_baseline $SCRATCH/compose_us_after1
```
Expected:INTC/MU/LITE/SNDK ✅(標題尾綴 `（GAAP，$M）` 由動態組回原字串 → 無 diff);**AAOI** 出現預期 diff:三表標題 `$M→$K` + FCF 列 ⏳→值(Task 1)。人工確認 AAOI diff 僅這兩類。

- [ ] **Step 10: Commit**

```bash
cd ~/CC_Switch_Config && git add skills/compose-financials/scripts skills/compose-financials/tests
git commit -m "feat(compose-financials): data-driven currency/scale (money_unit_label + eps NT$/\$ + title/ylabel templating + 3-statement multi-unit fail-loud); fixes AAOI \$M->\$K mislabel"
```

---

### Task 3: CONTRACT 條件旗標 + renderer 過濾 + NCI/台股權益條件列 + known_keys=rendered

**Files:**
- Modify: `.../compose_financials/contract.py`(加 `markets`/`render_if_present` 到台股條件列;加 `requires_source` 到 margins-nongaap;插 NCI/legal_reserve 條件列)
- Modify: `.../compose_financials/sections.py`(render_section 支援 render_if_present 隱藏列)
- Modify: `.../compose_financials/cli.py`(區塊過濾 pre-pass;known_keys=rendered set)
- Test: `.../tests/test_conditional.py`(新)

**Interfaces:**
- Consumes: record 集合(判斷 present)。
- Produces: `filter_sections(CONTRACT, market, idx, periods) -> list[spec]`(過濾掉 `requires_source` 缺來源 + `markets` 不含本市場的區塊/列);render_section 對 `render_if_present` 列缺值時**整列不出**;cli known_keys = 實際渲染區塊 key。

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_conditional.py
from compose_financials.contract import CONTRACT
from compose_financials.sections import render_section
from compose_financials.resolve import ValueIndex

def _idx(recs): return ValueIndex(recs)
def _r(stmt, ver, uni, per, val, unit="TWD_thousands"):
    return {"source":"gaap_facts","statement":stmt,"version":ver,"uni_account":uni,
            "period":per,"value":val,"unit":unit,"kind":None}

def test_render_if_present_hides_when_absent():
    # 一個 render_if_present 列,無值 → 整列不在輸出(不留 — 不留 ⏳)
    spec = {"key":"t","title":"T","statement":"BS","version":"GAAP","grain":"quarter","chart":None,
            "lines":[("Legal Reserve","legal_reserve","m",{"render_if_present":True}),
                     ("Total Equity","total_equity","m")]}
    body,_ = render_section(spec, _idx([_r("BS","GAAP","total_equity","Q1_FY2025",100)]),
                            ["Q1_FY2025"], [])
    assert "Legal Reserve" not in body
    assert "Total Equity" in body

def test_render_if_present_shows_when_present():
    spec = {"key":"t","title":"T","statement":"BS","version":"GAAP","grain":"quarter","chart":None,
            "lines":[("Legal Reserve","legal_reserve","m",{"render_if_present":True})]}
    body,_ = render_section(spec, _idx([_r("BS","GAAP","legal_reserve","Q1_FY2025",50)]),
                            ["Q1_FY2025"], [])
    assert "Legal Reserve" in body and "50" in body

def test_nci_conditional_rows_exist_in_contract():
    is_lines = [l for s in CONTRACT if s["key"]=="is" for l in s["lines"]]
    bs_lines = [l for s in CONTRACT if s["key"]=="bs" for l in s["lines"]]
    def _keys(lines): return [l[1] for l in lines if isinstance(l[1],str)]
    assert "net_income_nci" in _keys(is_lines)
    assert "minority_interest_bs" in _keys(bs_lines)
    assert "total_equity_incl_nci" in _keys(bs_lines)
    assert "legal_reserve" in _keys(bs_lines)
```

- [ ] **Step 2: 跑確認失敗**

Run: `python3 -m pytest tests/test_conditional.py -v`
Expected: FAIL(render 不支援 4-tuple flag;contract 無條件列)

- [ ] **Step 3: 支援 line 第 4 元素 flag(sections.py)**

CONTRACT line 允許 `(label, uni, fmt)` 或 `(label, uni, fmt, opts)`。render_section 迴圈解包:

```python
    for line in spec["lines"]:
        label, uni, fmt = line[0], line[1], line[2]
        opts = line[3] if len(line) > 3 else {}
        resolved = [_resolve_line(uni, spec.get("statement"), spec["version"], p, idx) for p in periods]
        values = [r[0] for r in resolved]
        if opts.get("render_if_present") and all(v is None for v in values):
            continue                     # 條件列缺值 → 整列不出
        # ...(其餘同現行:RATIO 全 None → ⏳;否則 fmt_value)
```

- [ ] **Step 4: contract.py 插 NCI/台股條件列 + requires_source**

IS `net_income_total_pre_nci`(line 30)後、`net_income`(line 32)前插:

```python
       ("　歸屬非控制權益 Net Income attrib. NCI", "net_income_nci", M, {"markets":("tw",), "render_if_present":True}),
```

BS `total_equity`(line 71)後插:

```python
       ("非控制權益 Minority Interest", "minority_interest_bs", M, {"markets":("tw",), "render_if_present":True}),
       ("**權益總計(含NCI) Total Equity incl. NCI**", "total_equity_incl_nci", M, {"markets":("tw",), "render_if_present":True}),
```

BS `retained_earnings`(line 68)前插:

```python
       ("法定盈餘公積 Legal Reserve", "legal_reserve", M, {"markets":("tw",), "render_if_present":True}),
```

margins-nongaap 區塊加:`"requires_source": "nongaap"`。

- [ ] **Step 5: cli.py 過濾 pre-pass + markets 列過濾 + known_keys=rendered**

在 `compose()` 迴圈前先算「本市場來源集合 + 各區塊是否渲染」:

```python
    sources_present = {r["source"] for r in recs}
    def _section_kept(spec):
        req = spec.get("requires_source")
        return (req is None) or (req in sources_present)
    kept_specs = [s for s in CONTRACT if _section_kept(s)]
```

markets 列過濾:render 前把不屬本市場的 line 濾掉(在 render_section 內或傳入前)。最簡:render_section 開頭過濾:

```python
    market = ...  # Task 4
    spec_lines = [l for l in spec["lines"]
                  if len(l) < 4 or "markets" not in l[3] or market in l[3]["markets"]]
```

(把 `spec["lines"]` 迴圈改用 `spec_lines`。)

迴圈只跑 `kept_specs`;`known_keys` 改:

```python
    new_doc = upsert(doc, blocks, order, known_keys=order)   # order = 實際渲染的 key,非全 CONTRACT
```

(`order` 已是逐區塊 append 的實渲染 key。)

- [ ] **Step 6: 跑條件測試 + 全套 + 美股回歸**

Run: `python3 -m pytest tests/ -q`
Expected: 全綠(既有美股:markets=("tw",) 列在 us 被濾掉 → 美股輸出不變;requires_source 只 margins-nongaap,美股 nongaap 來源在 → 不濾)。
再跑 `compose_regress.py`(us_baseline vs 新):INTC/MU/LITE/SNDK 仍只 3-diff、AAOI $K+FCF。

- [ ] **Step 7: Commit**

```bash
cd ~/CC_Switch_Config && git add skills/compose-financials
git commit -m "feat(compose-financials): conditional rows (markets/render_if_present) for TW NCI family + legal_reserve, requires_source section gating, known_keys=rendered set"
```

---

### Task 4: `--market tw` 接線(source discovery + in-memory flatten loader + CLI)

**Files:**
- Modify: `.../compose_financials/loaders.py`(market-aware base + tw facts reader)
- Modify: `.../compose_financials/cli.py`(`--market` arg + market-aware target path + thread market)
- Test: `.../tests/test_tw_loader.py`(新)

**Interfaces:**
- Consumes: `_shared.twse_canonical_facts.emit_canonical_facts`;Task 2/3 的 render/filter。
- Produces: `load_all(ticker, vault_root, market="us")`;tw → glob `MOPS Filings/.../parse-twse-ixbrl/{T}_twse_facts.json` → `emit_canonical_facts` → `_rec(source="gaap_facts", version="GAAP", ...)`,**排除 derive_base 進三表**(仍載 analytics);`--market {us,tw}` default us。

- [ ] **Step 1: 寫失敗測試(tmp 假 vault)**

```python
# tests/test_tw_loader.py
import json
from pathlib import Path
from compose_financials.loaders import load_all

def _mk_tw_vault(tmp: Path):
    d = tmp / "Khouse/Semiconductors/聯亞/01_Source/MOPS Filings/Skill_Output/parse-twse-ixbrl"
    d.mkdir(parents=True)
    (d / "3081_twse_facts.json").write_text(json.dumps({
        "ticker":"3081","report_category":"ir","unit":"TWD_thousands",
        "periods":["Q1_FY2026"],
        "facts_by_period":{"Q1_FY2026":{"period_end":"2026-03-31","report_category":"ir",
            "facts":{"revenue":{"value":904389.0,"statement":"income_statement","sort_order":4000,
                                "period_kind":"ytd","xbrl_concept":"ifrs-full:Revenue"},
                     "total_assets":{"value":5678137.0,"statement":"balance_sheet_assets",
                                "sort_order":1900,"period_kind":"instant","xbrl_concept":"ifrs-full:Assets"}}}}}))
    return tmp

def test_tw_load_flattens_and_tags_gaap_facts(tmp_path):
    v = _mk_tw_vault(tmp_path)
    recs = load_all("3081", v, market="tw")
    rev = [r for r in recs if r["uni_account"]=="revenue"]
    assert rev and rev[0]["source"]=="gaap_facts" and rev[0]["version"]=="GAAP"
    assert rev[0]["unit"]=="TWD_thousands" and rev[0]["value"]==904389.0
    assert rev[0]["statement"]=="IS"           # income_statement→IS
    ta = [r for r in recs if r["uni_account"]=="total_assets"]
    assert ta and ta[0]["statement"]=="BS" and ta[0]["period"]=="Q1_FY2026"

def test_tw_excludes_derive_base_from_statements(tmp_path):
    v = _mk_tw_vault(tmp_path)
    recs = load_all("3081", v, market="tw")
    assert not any(r["source"]=="derive_base" for r in recs)

def test_us_market_unchanged(tmp_path):
    # us 路徑仍讀 SEC Filings;無檔 → 空
    assert load_all("XXXX", tmp_path, market="us") == []
```

- [ ] **Step 2: 跑確認失敗**

Run: `python3 -m pytest tests/test_tw_loader.py -v`
Expected: FAIL(load_all 無 market 參數)

- [ ] **Step 3: 實作 loaders.py**

```python
import sys as _sys
_AI = Path(__file__).resolve()
# 找 AI_Agent/Tools/research-tools 上 sys.path(與 derive 同法)
for _up in _AI.parents:
    _cand = _up / "AI_Agent" / "Tools" / "research-tools"
    if _cand.exists():
        _sys.path.insert(0, str(_cand)); break

def _ticker_base(ticker, vault_root, market="us"):
    if market == "tw":
        hits = sorted(Path(vault_root).glob(
            f"Khouse/Semiconductors/*/01_Source/MOPS Filings/Skill_Output"))
        # 用含該 ticker facts 的資料夾
        for h in hits:
            if (h / "parse-twse-ixbrl" / f"{ticker}_twse_facts.json").exists():
                return h
        return None
    return Path(vault_root) / "Khouse/Semiconductors" / ticker / SKILL_OUTPUT
```

`load_all` 加 `market="us"`;tw 分支只載 twse facts(→ emit_canonical_facts → gaap_facts recs)+ derive-analytics(不載 derive_base、nongaap、supplement):

```python
def load_all(ticker, vault_root, market="us"):
    base = _ticker_base(ticker, vault_root, market)
    out = []
    if market == "tw":
        if base is None:
            raise FileNotFoundError(f"TW facts not found for {ticker} under MOPS Filings")
        from _shared.twse_canonical_facts import emit_canonical_facts
        tf = json.loads((base / "parse-twse-ixbrl" / f"{ticker}_twse_facts.json").read_text())
        for r in emit_canonical_facts(tf)["facts"]:
            out.append(_rec("gaap_facts", r["statement"], "GAAP",
                            r["uni_account"], r["period"], r["value"], r["unit"]))
        da = latest_run_dir(base / "derive-analytics")
        daj = _read_json(da / f"{ticker}_analytics.json") if da else None
        if daj:
            for r in daj.get("analytics_metrics", []):
                out.append(_rec("analytics", "RATIO", r.get("version","GAAP"),
                                r["uni_account"], r["period"], r["value"], r.get("unit"),
                                r.get("period_kind")))
        return out
    # ---- us 分支:現行 5 源不動 ----
    ...
```

- [ ] **Step 4: cli.py `--market` + market-aware target + thread**

```python
    ap.add_argument("--market", choices=("us","tw"), default="us")
    ...
    rep = compose(args.ticker, args.vault_root, args.quarters, args.years, overrides, market=args.market)
```

`compose(...)` 加 `market="us"`,傳 `load_all(ticker, vault_root, market)`;`_target_paths` 加 market:tw → glob 中文資料夾:

```python
def _target_paths(ticker, vault_root, market="us"):
    if market == "tw":
        hits = sorted(Path(vault_root).glob("Khouse/Semiconductors/*/01_Source/MOPS Filings/Skill_Output/parse-twse-ixbrl/%s_twse_facts.json" % ticker))
        if len(hits) != 1:
            raise ValueError(f"TW ticker folder glob for {ticker}: expected 1 hit, got {len(hits)}")
        root = hits[0].parents[3] / TRACKERS       # .../{中文名}/03_Working/Topics/Trackers
        return root / "Financials.md", root / "assets"
    root = Path(vault_root) / "Khouse/Semiconductors" / ticker / TRACKERS
    return root / "Financials.md", root / "assets"
```

`available_quarters` 錨點(cli.py:98)台股沒問題(revenue/GAAP/IS 台股也有);`compose()` 內把 `market` 傳給 render_section/filter/_maybe_chart(Task 2/3 的 market 參數這裡填實)。

- [ ] **Step 5: 跑 tw loader 測試 + 全套**

Run: `python3 -m pytest tests/ -q`
Expected: 全綠。

- [ ] **Step 6: Commit**

```bash
cd ~/CC_Switch_Config && git add skills/compose-financials
git commit -m "feat(compose-financials): --market tw wiring - MOPS glob source discovery, in-memory twse_canonical_facts flatten (source=gaap_facts), exclude derive_base from TW statements, market-aware target path"
```

---

### Task 5: 聯亞/台達電 端到端 smoke + 幕等 + parity snapshot 測試

**Files:**
- Test: `.../tests/test_frontend_parity.py`(新)
- Output: `$SCRATCH/compose_tw_smoke.md`(人工核對記錄)

**Interfaces:**
- Consumes: 前端 `constants.ts`(算 parity delta)、CONTRACT。

- [ ] **Step 1: parity snapshot 測試**

前端 constants.ts 已含 `net_income_nci`(IS_ROWS),故真正「compose 條件列 − 前端」delta 只 3 個。測試斷言此**校正後**集合:

```python
# tests/test_frontend_parity.py
import re
from pathlib import Path
from compose_financials.contract import CONTRACT

CONSTANTS = Path("/Users/mensch5566/AI_Agent/app/components/financials-v2/constants.ts")

def _frontend_keys():
    txt = CONSTANTS.read_text()
    # 抓 IS_ROWS/BS_ROWS/CF_ROWS 內的 uni_account 字串鍵
    return set(re.findall(r'uni_account:\s*"([a-z0-9_]+)"', txt)) or \
           set(re.findall(r'"([a-z0-9_]+)"', txt))

def _tw_conditional_keys():
    out = set()
    for sec in CONTRACT:
        for line in sec.get("lines", []):
            if len(line) > 3 and "tw" in (line[3].get("markets") or ()):
                if isinstance(line[1], str):
                    out.add(line[1])
    return out

def test_frontend_parity_delta_is_tracked():
    tw_cond = _tw_conditional_keys()
    assert tw_cond == {"legal_reserve","net_income_nci","minority_interest_bs","total_equity_incl_nci"}
    # net_income_nci 已在前端 constants.ts;真正前端缺的只有 3 個
    delta = tw_cond - _frontend_keys()
    assert delta == {"legal_reserve","minority_interest_bs","total_equity_incl_nci"}, \
        f"frontend-parity delta drifted: {delta}"
```

(若 `_frontend_keys` 正則抓不到,實作時對 constants.ts 實際格式微調——目標是取到 IS/BS/CF 的 key 集合。)

- [ ] **Step 2: 跑 parity 測試**

Run: `python3 -m pytest tests/test_frontend_parity.py -v`
Expected: PASS(調正則到抓對為止)

- [ ] **Step 3: sync 後跑真實 smoke**

```bash
cd ~/CC_Switch_Config && bash scripts/sync-to-local.sh
cd ~/CC_Switch_Config/skills/compose-financials/scripts
python3 -m compose_financials.cli 3081 --market tw
python3 -m compose_financials.cli 2308 --market tw
```
Expected:各印 `composed N sections`。

- [ ] **Step 4: 人工核對聯亞 Financials.md(寫進 $SCRATCH/compose_tw_smoke.md)**

檢查:(a) 三表數字對 `3081_twse_facts.json`(revenue Q1_FY2026=904389、total_assets=5678137、**capex 負**);(b) **無** Non-GAAP 區塊;(c) bs-structure 圖**有**產;(d) 標題 `（IFRS，NT$ 仟元）`、EPS `NT$`;(e) 無 Q2-Q4 CF 單季滲入 derive_base 值(留白);(f) margins/growth/liquidity/returns 填滿。台達電(cr)另核 `minority_interest_bs`/`total_equity_incl_nci` 條件列有出現。

- [ ] **Step 5: 幕等驗證**

```bash
# 聯亞頁手寫一段 Observations(marker 外),重跑,確認保留
F=~/Obsidian/Khouse/Semiconductors/聯亞/03_Working/Topics/Trackers/Financials.md
printf '\n## My Observations\n手寫測試內容\n' >> "$F"
python3 -m compose_financials.cli 3081 --market tw
grep -q "手寫測試內容" "$F" && echo "✅ 幕等保留" || echo "❌ 幕等破壞"
```
Expected: ✅

---

### Task 6: docs + sync + 收尾

**Files:**
- Modify: `.../compose-financials/SKILL.md`(v2:台股 in-scope、`--market`、unit 驅動、條件列、區塊過濾)
- Modify: `~/AI_Agent/docs/STATUS.md`(compose 台股支援 + parity delta note)
- Modify: memory `project_financials_skill_naming_refactor.md`(compose 台股完成)

- [ ] **Step 1: SKILL.md v2**

scope 表台股改 `v2 in-scope`;加 `--market tw` 用法 + unit 驅動 + 條件列 + requires_source + frontend-parity delta(3 key,tracked)說明。

- [ ] **Step 2: 最終美股回歸 + 全測試 + sync**

```bash
cd ~/CC_Switch_Config/skills/compose-financials && python3 -m pytest tests/ -q     # 全綠
mkdir -p "$SCRATCH/compose_us_final"
for T in INTC MU LITE SNDK AAOI; do
  (cd scripts && python3 -m compose_financials.cli $T >/dev/null 2>&1)
  cp ~/Obsidian/Khouse/Semiconductors/$T/03_Working/Topics/Trackers/Financials.md "$SCRATCH/compose_us_final/${T}_Financials.md"
done
python3 $SCRATCH/compose_regress.py $SCRATCH/compose_us_baseline $SCRATCH/compose_us_final   # 僅 3-diff/AAOI
cd ~/CC_Switch_Config && bash scripts/sync-to-local.sh
ls ~/.claude/skills/compose-financials/scripts/compose_financials/loaders.py   # mirror 存在
```

- [ ] **Step 3: Commit + memory**

```bash
cd ~/CC_Switch_Config && git add -A && git commit -m "docs(compose-financials): v2 SKILL.md - TW in-scope, --market, unit-driven currency, conditional rows, parity delta"
cd ~/AI_Agent && git add docs/STATUS.md && git commit -m "docs(STATUS): compose-financials TW support (聯亞/台達電) via --market tw"
```
更新 memory + save_memory 完工摘要。

---

## Self-Review 紀錄

- **Spec coverage**:§3.1→T4、§3.2→T2、§3.3(FCF)→T1 (NCI/條件列)→T3、§3.4→T3、§3.5→T6、§4 gate→T0/T2/T5、backlog→未做(登記在案)。
- **Placeholder scan**:無 TBD;code 步驟含完整 before/after。
- **Type consistency**:`load_all(ticker,vault_root,market)`、`render_section(...,regime,money_label)`、`money_unit_label`、`_ticker_base(...,market)`、`_target_paths(...,market)` 跨 task 一致。
- **修正的 spec 不準**:§4 parity 公式把 `net_income_nci` 算進「前端缺」是錯的(它已在 constants.ts IS_ROWS)→ T5 測試改斷言校正後 3-key delta(legal_reserve/minority_interest_bs/total_equity_incl_nci),並在斷言註明 net_income_nci 已在前端。
