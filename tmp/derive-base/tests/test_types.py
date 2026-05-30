from derive_types import DerivedMetricRow

def test_derived_metric_row_minimal():
    r = DerivedMetricRow(
        cell_id="abc123",
        ticker="AAOI",
        period="Q4_FY2024",
        period_kind="derived_q4",
        period_start="2024-10-01",
        period_end="2024-12-31",
        statement="IS",
        version="GAAP",
        uni_account="revenue",
        value=65200.0,
        unit="USD_thousands",
        status="DERIVED_FROM_DISCLOSED",
        provenance={"rule_id": "Q4_FY_MINUS_9M", "chain_depth": 1, "inputs": []},
    )
    assert r.status == "DERIVED_FROM_DISCLOSED"
    assert r.period_kind == "derived_q4"
