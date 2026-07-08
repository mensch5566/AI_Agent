"""TWSE parse facts → FactRow adapter(市場無關 derive 的台股入口)。

鏡像 sec_json_adapter:derive engine 只認 FactRow,本模組把
parse-twse-ixbrl 的 {TICKER}_twse_facts.json(facts_by_period keyed-dict)
攤平成 FactRow list。Spec:
docs/superpowers/specs/2026-07-02-derive-market-agnostic-design.md §4。

轉換規則(spec §4 表):
  2a  IS/CF duration:Q1 ytd→Q1_FY(單季);Q2/Q3 ytd→6M/9M_FY;年報→FY
  2b  BS instant:恆為 Q{n}_FY —— 年報期末 BS = Q4_FY(rules_crossperiod
      的年度比率用 Q4_FY label 查期末餘額;標成 FY 會整組靜默跳過)
  3   __q 揭露單季 → Q{n}_FY quarter_duration,SOURCE_OF_TRUTH(揭露值優先;
      engine rules_q2q3/rules_q4 看到單季已存在即跳過重建)
  4   unit:每 row TWD_thousands;EPS row TWD_per_share
  7   符號:capital_expenditures 翻成正支出(共用 FCF 規則 coef=-1 的 SEC 慣例);
      淨流量(investing/financing/operating/fx/net_change)維持帶號
  8   beginning_cash/ending_cash 為餘額非流量,排除於 fact 流(rules_q4 選
      重建對象只看 statement+unit,餘額會被 FY−9M 硬算)
"""
from __future__ import annotations

from . import cell_id as _id
from .period_kind import infer_period_kind
from .sec_json_adapter import CompanyRow, FactRow

_STMT_MAP = {
    "income_statement": "IS",
    "balance_sheet_assets": "BS",
    "balance_sheet_liabilities": "BS",
    "balance_sheet_equity": "BS",
    "cash_flow_operating": "CF",
    "cash_flow_investing": "CF",
    "cash_flow_financing": "CF",
    "cash_flow_summary": "CF",
}
_EPS_UNIS = {"eps_basic", "eps_diluted"}
# CF 現金「餘額」(非流量)— 不得進入重建 fact 流(spec §4 規則 8)。
_CASH_BALANCE_KEYS = {"beginning_cash", "ending_cash"}
# 台股 CF 帶號加總慣例 → 共用引擎期望「正的支出」的科目(spec §4 規則 7)。
_SIGN_FLIP_TO_POSITIVE_OUTFLOW = {"capital_expenditures"}

# Public contract for display-layer consumers (compose-financials loaders):
# the exact set of CF keys this adapter flips to positive-outflow on derive ingest.
# Display layers use it to flip derived values BACK to as-reported sign convention.
SIGN_FLIP_TO_POSITIVE_OUTFLOW = _SIGN_FLIP_TO_POSITIVE_OUTFLOW


def adapt_company_twse(facts_json: dict) -> CompanyRow:
    t = str(facts_json["ticker"])
    return CompanyRow(ticker=t, company_name=t, exchange="TWSE", cik="",
                      currency="TWD", fiscal_year_end_month=12,
                      filings={}, sign_flip_concepts=[])


def _period_label(period: str, stmt: str, is_q_variant: bool) -> str:
    q, fy = period.split("_FY")
    qn = int(q[1])
    if stmt == "BS":
        return period            # 2b:年末 BS = Q4_FY{Y},季 BS = Q{n}_FY{Y}
    if is_q_variant or qn == 1:
        return period            # 3 / 2a:揭露單季、Q1 ytd 即單季
    if qn == 4:
        return f"FY{fy}"         # 2a:年報 IS/CF 累計
    return f"{qn * 3}M_FY{fy}"   # 2a:6M / 9M


def adapt_twse_facts(facts_json: dict) -> list[FactRow]:
    ticker = str(facts_json["ticker"])
    top_unit = facts_json.get("unit")
    if top_unit != "TWD_thousands":
        raise ValueError(f"unexpected TWSE facts unit: {top_unit!r} (fail-closed)")
    rows: list[FactRow] = []
    for period, pdata in facts_json.get("facts_by_period", {}).items():
        period_end = pdata.get("period_end")
        cat = pdata.get("report_category")
        for key, fact in pdata.get("facts", {}).items():
            is_q = key.endswith("__q")
            base = key[:-3] if is_q else key
            # Defense-in-depth: Q1 must never carry __q key (Q1 YTD is already the single quarter)
            if period.split("_FY")[0] == "Q1" and is_q:
                raise ValueError(
                    f"Q1 must not carry a __q single-quarter key (Q1 YTD is already the single quarter): {period}/{key}"
                )
            if base in _CASH_BALANCE_KEYS:
                continue
            stmt = _STMT_MAP[fact["statement"]]
            label = _period_label(period, stmt, is_q)
            unit = "TWD_per_share" if base in _EPS_UNIS else "TWD_thousands"
            value = float(fact["value"])
            if base in _SIGN_FLIP_TO_POSITIVE_OUTFLOW:
                value = -value
            period_kind = infer_period_kind(stmt, label)
            concept = fact.get("xbrl_concept") or ""
            provenance = {
                "source_filing": "TWSE_iXBRL",
                "market": "TW",
                "report_category": cat,
                "substatement": fact["statement"],
                "disclosed_single_quarter": is_q,
            }
            cid = _id.facts_cell_id(
                ticker=ticker, period=label, period_kind=period_kind,
                version="GAAP", statement=stmt, uni_account=base,
                source_account=concept, xbrl_tag=concept or None,
            )
            rows.append(FactRow(
                cell_id=cid, ticker=ticker, period=label, period_end=period_end,
                period_kind=period_kind, statement=stmt, version="GAAP",
                uni_account=base, source_account=concept, xbrl_tag=concept or None,
                value=value, weight=1, unit=unit, status="SOURCE_OF_TRUTH",
                ordinal=None, long_tail_metadata=None, provenance=provenance,
            ))
    return rows


def reconcile_disclosed_quarters(facts_json: dict, tol: float = 0.0) -> list[dict]:
    """spec §4 __q 對帳:__q 升格後 engine 跳過重建 → conflicts 統計抓不到
    「揭露單季 vs YTD 差」;此函式補上該檢查。per-share(EPS)非加性,跳過。"""
    fbp = facts_json.get("facts_by_period", {})
    out: list[dict] = []
    for period, pdata in fbp.items():
        q, fy = period.split("_FY")
        qn = int(q[1])
        prior_facts = fbp.get(f"Q{qn - 1}_FY{fy}", {}).get("facts", {})
        for key, fact in pdata.get("facts", {}).items():
            if not key.endswith("__q"):
                continue
            base = key[:-3]
            if base in _EPS_UNIS:
                out.append({"period": period, "uni_account": base,
                            "status": "SKIPPED_NON_ADDITIVE",
                            "disclosed_q": fact["value"]})
                continue
            cur = pdata["facts"].get(base)
            prev = prior_facts.get(base)
            if cur is None or prev is None:
                out.append({"period": period, "uni_account": base,
                            "status": "MISSING_YTD_INPUT",
                            "disclosed_q": fact["value"]})
                continue
            expected = cur["value"] - prev["value"]
            diff = fact["value"] - expected
            out.append({"period": period, "uni_account": base,
                        "status": "MATCH" if abs(diff) <= tol else "MISMATCH",
                        "disclosed_q": fact["value"], "ytd_diff": expected,
                        "diff": diff})
    return out
