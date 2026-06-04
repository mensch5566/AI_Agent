"""Engine-level integration: Q2/Q3 single-quarter reconstruction is wired into
Pass 2 and Pass 3 identity treats derived_q2/derived_q3 like derived_q4.

Scenario: a YTD-first-class parse where revenue + cost_of_goods_sold are
disclosed only as Q1 / 6M / 9M / FY (no direct Q2/Q3, no direct gross_profit).
The engine must rebuild the Q2/Q3 single quarters AND the gross_profit subtotal
at those derived single quarters.
"""
import sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent.parent / "Tools" / "research-tools"))

from derive_engine import run_engine
from _shared.sec_json_adapter import FactRow


def _row(uni, tag, period, kind, end, value):
    return FactRow(
        cell_id=f"{uni}:{period}", ticker="ZZ", period=period, period_end=end,
        period_kind=kind, statement="IS", version="GAAP", uni_account=uni,
        source_account=f"us-gaap:{tag}", xbrl_tag=tag, value=value, weight=1,
        unit="USD_thousands", status="SOURCE_OF_TRUTH", ordinal=None,
        long_tail_metadata=None, provenance={"source_filing": "10-Q"},
    )


def _ytd_only_is_facts():
    facts = []
    for uni, tag, (q1, h1, n9, fy) in [
        ("revenue", "Revenues", (40000.0, 83000.0, 148000.0, 249000.0)),
        ("cost_of_goods_sold", "CostOfGoodsSold", (20000.0, 42000.0, 75000.0, 130000.0)),
    ]:
        facts += [
            _row(uni, tag, "Q1_FY2024", "quarter_duration",   "2024-03-31", q1),
            _row(uni, tag, "6M_FY2024", "ytd_duration",        "2024-06-30", h1),
            _row(uni, tag, "9M_FY2024", "ytd_duration",        "2024-09-30", n9),
            _row(uni, tag, "FY2024",    "fy_annual_duration",  "2024-12-31", fy),
        ]
    return facts


def _by(rows, uni, period):
    return next((r for r in rows if r.uni_account == uni and r.period == period), None)


def test_engine_rebuilds_q2_q3_single_quarters():
    result = run_engine(facts=_ytd_only_is_facts(), calc_rules={}, qname_to_uni={})
    rows = result["winners"]

    # revenue single quarters
    assert _by(rows, "revenue", "Q2_FY2024").value == 43000.0   # 83000 − 40000
    assert _by(rows, "revenue", "Q3_FY2024").value == 65000.0   # 148000 − 83000
    assert _by(rows, "revenue", "Q4_FY2024").value == 101000.0  # 249000 − 148000
    # cogs single quarters
    assert _by(rows, "cost_of_goods_sold", "Q2_FY2024").value == 22000.0
    assert _by(rows, "cost_of_goods_sold", "Q3_FY2024").value == 33000.0

    # period_kind labelling
    assert _by(rows, "revenue", "Q2_FY2024").period_kind == "derived_q2"
    assert _by(rows, "revenue", "Q3_FY2024").period_kind == "derived_q3"


def test_engine_derives_subtotal_at_q2_q3():
    # gross_profit is not disclosed at all; identity (revenue − cogs) must hold
    # at the derived single quarters too.
    result = run_engine(facts=_ytd_only_is_facts(), calc_rules={}, qname_to_uni={})
    rows = result["winners"]
    gp_q2 = _by(rows, "gross_profit", "Q2_FY2024")
    gp_q3 = _by(rows, "gross_profit", "Q3_FY2024")
    assert gp_q2 is not None and gp_q2.value == 21000.0          # 43000 − 22000
    assert gp_q3 is not None and gp_q3.value == 32000.0          # 65000 − 33000
    assert gp_q2.period_kind == "derived_q2"


def test_engine_stats_count_q2q3():
    result = run_engine(facts=_ytd_only_is_facts(), calc_rules={}, qname_to_uni={})
    s = result["stats"]
    # Pass 2 now emits Q2+Q3+Q4 for the inputs it can rebuild (>= 6 single
    # quarters: revenue/cogs × Q2/Q3/Q4, plus any chained subtotals).
    assert s["pass2_count"] >= 6
    assert s["conflicts"] == 0
    # q2q3 skip diagnostics surfaced in stats/result
    assert "q2q3_skips" in s
    assert "q2q3_skips" in result


def test_direct_quarters_not_reconstructed():
    # If Q2/Q3 are directly disclosed, the engine must not emit derived rows
    # for them (no spurious derived_q2/derived_q3).
    facts = _ytd_only_is_facts() + [
        _row("revenue", "Revenues", "Q2_FY2024", "quarter_duration", "2024-06-30", 43000.0),
        _row("revenue", "Revenues", "Q3_FY2024", "quarter_duration", "2024-09-30", 65000.0),
    ]
    result = run_engine(facts=facts, calc_rules={}, qname_to_uni={})
    rows = result["winners"]
    rev_q2 = _by(rows, "revenue", "Q2_FY2024")
    # The direct fact is SOURCE_OF_TRUTH and filtered out of derived winners;
    # the engine must not produce a derived revenue Q2 that duplicates it.
    assert rev_q2 is None  # filter_against_facts drops the derived dup
