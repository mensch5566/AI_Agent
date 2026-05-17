from audit import to_derived_metric_row
from derive_types import Candidate


def _c():
    return Candidate(
        ticker="AAOI", period="Q4_FY2024", period_kind="derived_q4",
        period_start="2024-10-01", period_end="2024-12-31",
        statement="IS", version="GAAP", uni_account="revenue",
        value=101000.0, unit="USD_thousands",
        rule_id="Q4_FY_MINUS_9M", rule_priority=1,
        chain_depth=1, chained=False,
        inputs=[{"cell_id": "fy", "uni_account": "revenue", "period": "FY2024", "value": 249000.0, "status": "SOURCE_OF_TRUTH"}],
        extras={"formula": "FY2024 - 9M_FY2024"},
    )


def test_to_derived_metric_row_deterministic_cell_id():
    a = to_derived_metric_row(_c())
    b = to_derived_metric_row(_c())
    assert a.cell_id == b.cell_id
    assert a.status == "DERIVED_FROM_DISCLOSED"
    assert a.provenance["rule_id"] == "Q4_FY_MINUS_9M"
    assert a.provenance["formula"] == "FY2024 - 9M_FY2024"
    assert a.provenance["chain_depth"] == 1
    assert a.provenance["target_table"] == "sec_financial_metrics"
