"""台股 facts 收斂成 canonical long-format(給 compose / display / 下游 consumer)。

parse-twse-ixbrl 輸出 `{T}_twse_facts.json` 是 keyed-dict(`facts_by_period`);美股
`{T}_gaap_facts.json` 是 long-format(`facts: [...]`)。本模組把台股 keyed-dict **忠實
(as-reported)** 攤平成同一個 long-format shape,讓 compose 等 consumer 用同一條 read path。

跟 `twse_json_adapter`(derive 用)的差別:
- adapter 為 derive engine 服務 → capex 翻正、排除 beginning/ending_cash、升 __q。
- 本模組為 **display / as-reported** 服務 → **不翻 capex 符號、保留現金餘額**,值一律照
  parse 揭露。共用的只有 period relabel(`_period_label`)與 statement map(`_STMT_MAP`），
  確保 period 命名與美股/derive 一致(Q2 ytd→6M、__q→Q2 單季、年末 BS→Q4_FY）。
"""
from __future__ import annotations

import json
from pathlib import Path

from . import cell_id as _id
from .period_kind import infer_period_kind
from .sec_json_adapter import FactRow
from .twse_json_adapter import _EPS_UNIS, _STMT_MAP, _period_label


def emit_canonical_facts(facts_json: dict) -> dict:
    """keyed-dict `facts_by_period` → long-format `{metadata, facts: [...]}`（as-reported）。

    每筆 fact 輸出 compose/gaap_facts 契約欄位:
      period, period_end, statement(IS/BS/CF), uni_account, value, unit,
      source_account(= xbrl_concept), period_kind(ytd/instant/quarter，原樣保留供 audit)
    """
    ticker = str(facts_json["ticker"])
    top_unit = facts_json.get("unit")
    if top_unit != "TWD_thousands":
        raise ValueError(f"unexpected TWSE facts unit: {top_unit!r} (fail-closed)")

    out_facts: list[dict] = []
    for period, pdata in facts_json.get("facts_by_period", {}).items():
        period_end = pdata.get("period_end")
        for key, fact in pdata.get("facts", {}).items():
            is_q = key.endswith("__q")
            base = key[:-3] if is_q else key
            stmt = _STMT_MAP[fact["statement"]]
            label = _period_label(period, stmt, is_q)
            unit = "TWD_per_share" if base in _EPS_UNIS else "TWD_thousands"
            concept = fact.get("xbrl_concept") or ""
            out_facts.append({
                "period": label,
                "period_end": period_end,
                "statement": stmt,
                "uni_account": base,
                "value": float(fact["value"]),      # as-reported，不翻號
                "unit": unit,
                "source_account": concept,
                "period_kind": fact.get("period_kind"),
            })

    return {
        "metadata": {
            "ticker": ticker,
            "schema_version": "twse_canonical_v1_long_format",
            "report_category": facts_json.get("report_category"),
            "unit": top_unit,
            "source": "parse-twse-ixbrl (facts_by_period) flattened as-reported",
            "row_count": len(out_facts),
            "periods": sorted({r["period"] for r in out_facts}),
        },
        "facts": out_facts,
    }


def adapt_twse_canonical_facts(facts_json: dict) -> list[FactRow]:
    """As-reported TWSE facts → FactRow list for the DB `sec_financial_facts` layer.

    Storage sibling of emit_canonical_facts: same as-reported semantics (capex kept
    negative, cash balances preserved, no __q dedup) but emits FactRow with the DB
    contract (cell_id / inferred period_kind / status=SOURCE_OF_TRUTH / version=GAAP
    / provenance market=TW). Distinct from twse_json_adapter.adapt_twse_facts, which
    applies derive-only transforms (capex→positive, cash-balance exclusion) and must
    NOT feed the display/SSOT facts table.
    """
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
            stmt = _STMT_MAP[fact["statement"]]
            label = _period_label(period, stmt, is_q)
            unit = "TWD_per_share" if base in _EPS_UNIS else "TWD_thousands"
            value = float(fact["value"])            # as-reported — no capex sign flip
            period_kind = infer_period_kind(stmt, label)
            concept = fact.get("xbrl_concept") or ""
            provenance = {
                "source_filing": "TWSE_iXBRL",
                "market": "TW",
                "as_reported": True,
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


def _default_out_path(twse_facts_path: Path) -> Path:
    # 與 twse_facts.json 同目錄，檔名 {T}_twse_facts_canonical.json
    stem = twse_facts_path.name.replace("_twse_facts.json", "_twse_facts_canonical.json")
    return twse_facts_path.parent / stem


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="台股 facts → canonical long-format(as-reported)")
    ap.add_argument("--in", dest="in_path", required=True, help="{T}_twse_facts.json 路徑")
    ap.add_argument("--out", dest="out_path", help="輸出路徑(預設同目錄 _canonical.json)")
    args = ap.parse_args(argv)
    in_path = Path(args.in_path)
    doc = json.loads(in_path.read_text())
    out = emit_canonical_facts(doc)
    out_path = Path(args.out_path) if args.out_path else _default_out_path(in_path)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"✅ {out['metadata']['ticker']}: {out['metadata']['row_count']} facts "
          f"({len(out['metadata']['periods'])} periods) → {out_path}")


if __name__ == "__main__":
    main()
