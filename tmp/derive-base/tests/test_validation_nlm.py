"""Tests for derive-base NLM validation (validation_nlm.py)."""

from __future__ import annotations
from validation_nlm import (
    validate_derived, _q4_from_fy_and_ytd, _tolerance_for_unit,
)


def test_q4_decomposition_helper():
    assert _q4_from_fy_and_ytd("Q4_FY2024") == (
        "FY2024", ["Q1_FY2024", "Q2_FY2024", "Q3_FY2024"]
    )
    assert _q4_from_fy_and_ytd("Q1_FY2024") is None
    assert _q4_from_fy_and_ytd("6M_FY2024") is None
    assert _q4_from_fy_and_ytd("FY2024") is None


def test_direct_match_passes_within_tolerance():
    derived = [{"period": "Q4_FY2024", "uni_account": "revenue", "value": 100.0,
                "unit": "USD_millions", "provenance": {"rule_id": "Q4_FY_MINUS_9M"}}]
    nlm = {"Q4_FY2024": [{"label": "Net revenue", "value": 100.2, "unit": "USD_millions"}]}
    label_map = {"Net revenue": "revenue"}
    rep = validate_derived(derived, nlm, label_map)
    assert rep["counts"]["passed"] == 1
    assert rep["passed"][0]["method"] == "direct"


def test_direct_match_fails_outside_tolerance():
    derived = [{"period": "Q1_FY2024", "uni_account": "revenue", "value": 100.0,
                "unit": "USD_millions", "provenance": {}}]
    nlm = {"Q1_FY2024": [{"label": "Net revenue", "value": 105.0, "unit": "USD_millions"}]}
    label_map = {"Net revenue": "revenue"}
    rep = validate_derived(derived, nlm, label_map)
    assert rep["counts"]["failed"] == 1
    assert rep["failed"][0]["diff"] == 5.0


def test_q4_reconstruct_from_fy_minus_q1q2q3():
    """If derive produces Q4_FY{y} but NLM only has Q1/Q2/Q3/FY,
    validation reconstructs expected Q4 = FY - (Q1+Q2+Q3) for comparison."""
    derived = [{"period": "Q4_FY2024", "uni_account": "revenue", "value": 25.0,
                "unit": "USD_millions", "provenance": {"rule_id": "Q4_FY_MINUS_9M"}}]
    nlm = {
        "FY2024":   [{"label": "Net revenue", "value": 100.0, "unit": "USD_millions"}],
        "Q1_FY2024":[{"label": "Net revenue", "value": 25.0,  "unit": "USD_millions"}],
        "Q2_FY2024":[{"label": "Net revenue", "value": 25.0,  "unit": "USD_millions"}],
        "Q3_FY2024":[{"label": "Net revenue", "value": 25.0,  "unit": "USD_millions"}],
    }
    label_map = {"Net revenue": "revenue"}
    rep = validate_derived(derived, nlm, label_map)
    assert rep["counts"]["passed"] == 1
    assert rep["passed"][0]["method"] == "q4_reconstruct_fy_minus_q1q2q3"
    # NLM expected = 100 - (25+25+25) = 25, matches derived 25
    assert rep["passed"][0]["nlm"] == 25.0


def test_sign_flipped_treated_as_pass():
    """XBRL stores interest_expense positive (e.g. 26.5), NLM PDF gives -26.5.
    Same magnitude, opposite sign → validation should pass with sign_flipped=True."""
    derived = [{"period": "Q4_FY2022", "uni_account": "interest_expense", "value": 26.5,
                "unit": "USD_millions", "provenance": {"rule_id": "Q4_FY_MINUS_9M"}}]
    nlm = {"Q4_FY2022": [{"label": "Interest expense", "value": -26.5, "unit": "USD_millions"}]}
    label_map = {"Interest expense": "interest_expense"}
    rep = validate_derived(derived, nlm, label_map)
    assert rep["counts"]["passed"] == 1
    assert rep["passed"][0]["sign_flipped"] is True


def test_unmatched_when_no_nlm_for_period_uni():
    derived = [{"period": "6M_FY2024", "uni_account": "revenue", "value": 50.0,
                "unit": "USD_millions", "provenance": {}}]
    nlm = {"Q1_FY2024": [{"label": "Net revenue", "value": 25.0, "unit": "USD_millions"}]}
    label_map = {"Net revenue": "revenue"}
    rep = validate_derived(derived, nlm, label_map)
    assert rep["counts"]["unmatched"] == 1
    assert rep["unmatched"][0]["period"] == "6M_FY2024"


def test_label_to_key_null_mapping_skipped():
    """LITE config maps some PDF labels to null (section headers / memo lines).
    load_cross_check_label_map already filters those; validate_derived also
    must defensively skip when label_to_key.get(label) is falsy."""
    derived = [{"period": "Q4_FY2024", "uni_account": "revenue", "value": 100.0,
                "unit": "USD_millions", "provenance": {}}]
    nlm = {"Q4_FY2024": [
        {"label": "Operating expenses:", "value": 0.0, "unit": "USD_millions"},  # section header
        {"label": "Net revenue",         "value": 100.0, "unit": "USD_millions"},
    ]}
    # label_to_key includes the null entry as an empty mapping (filtered out)
    label_map = {"Net revenue": "revenue"}
    rep = validate_derived(derived, nlm, label_map)
    assert rep["counts"]["passed"] == 1
    assert rep["passed"][0]["nlm"] == 100.0


def test_tolerance_per_unit():
    assert _tolerance_for_unit("USD_per_share") == 0.01
    assert _tolerance_for_unit("USD_millions") == 0.5
    assert _tolerance_for_unit("Pure") == 0.001
    assert _tolerance_for_unit("USD_thousands") == 0.5  # default
