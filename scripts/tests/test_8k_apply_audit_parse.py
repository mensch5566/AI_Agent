"""Regression tests for parse-8k-nongaap apply_audit.parse_review_md.

F6 fix: parser was indexing fixed columns; new extract output has 9 cols
(extra `match` + `audit_internal_key`). The old code would silently treat
NLM values as audit_value, polluting audit provenance.

Run: uv run --with pytest python3 -m pytest scripts/tests/test_8k_apply_audit_parse.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "Tools" / "research-tools"))
sys.path.insert(
    0,
    "/Users/mensch5566/CC_Switch_Config/skills/parse-8k-nongaap/scripts",
)

import apply_audit  # noqa: E402


MAIN_HEADER = (
    "| period | display_label (8-K) | internal_key | match | NLM Non-GAAP | "
    "audit_internal_key | audit_value | audit_note | unit |"
)
MAIN_SEP = "|---|---|---|---|---|---|---|---|---|"

UNMAPPED_HEADER = (
    "| period | label | NLM value | unit | audit_internal_key | "
    "audit_value | audit_note |"
)
UNMAPPED_SEP = "|---|---|---|---|---|---|---|"


def _write(tmp_path, lines):
    p = tmp_path / "review.md"
    p.write_text("\n".join(lines) + "\n")
    return p


# ─────────────────────────────────────────────────────────────────────────────
# F6 main-table tests
# ─────────────────────────────────────────────────────────────────────────────

def test_empty_audit_value_returns_no_rows(tmp_path):
    """The F6 bug: row with empty audit_value was being parsed as if NLM
    Non-GAAP was audit_value, then written back as `audit_source=PDF`."""
    md = _write(tmp_path, [
        MAIN_HEADER, MAIN_SEP,
        "| Q1_FY2020 | Gross profit | `gross_profit` | HARD | 206.1 |  |  |  | $ millions |",
    ])
    audits = apply_audit.parse_review_md(md, {})
    assert audits == []


def test_filled_audit_value_parses_correctly(tmp_path):
    md = _write(tmp_path, [
        MAIN_HEADER, MAIN_SEP,
        "| Q1_FY2020 | Adj. EPS | `adj_eps` | HARD | 0.45 |  | 0.48 | corrected | USD_per_share |",
    ])
    audits = apply_audit.parse_review_md(md, {})
    assert len(audits) == 1
    a = audits[0]
    assert a["period"] == "Q1_FY2020"
    assert a["display_label"] == "Adj. EPS"
    assert a["internal_key"] == "adj_eps"
    assert a["nlm_value"] == 0.45
    assert a["audit_value"] == 0.48
    assert a["audit_note"] == "corrected"
    assert a["unit"] == "USD_per_share"


def test_audit_internal_key_overrides_internal_key(tmp_path):
    """When audit_internal_key is filled, it should win (LLM mis-inferred,
    user corrects)."""
    md = _write(tmp_path, [
        MAIN_HEADER, MAIN_SEP,
        "| Q1_FY2020 | Adj. EBITDA | `wrong_key` | LLM(0.7) | 100 | "
        "`adj_ebitda` | 105 | LLM miss | USD_millions |",
    ])
    audits = apply_audit.parse_review_md(md, {})
    assert audits[0]["internal_key"] == "adj_ebitda"


def test_mixed_filled_and_empty_only_filled_kept(tmp_path):
    md = _write(tmp_path, [
        MAIN_HEADER, MAIN_SEP,
        "| Q1_FY2020 | Revenue | `revenue` | HARD | 500 |  |  |  | USD_millions |",
        "| Q1_FY2020 | Adj. EPS | `adj_eps` | HARD | 0.45 |  | 0.48 | x | USD_per_share |",
        "| Q2_FY2020 | Revenue | `revenue` | HARD | 600 |  |  |  | USD_millions |",
    ])
    audits = apply_audit.parse_review_md(md, {})
    assert len(audits) == 1
    assert audits[0]["display_label"] == "Adj. EPS"
    assert audits[0]["audit_value"] == 0.48


def test_unit_propagation_per_row(tmp_path):
    """F4 + F6: per-row unit must propagate (small-cap USD_thousands)."""
    md = _write(tmp_path, [
        MAIN_HEADER, MAIN_SEP,
        "| Q1_FY2020 | Revenue | `revenue` | HARD | 50000 |  | 51000 | small-cap | USD_thousands |",
    ])
    audits = apply_audit.parse_review_md(md, {})
    assert audits[0]["unit"] == "USD_thousands"


# ─────────────────────────────────────────────────────────────────────────────
# F6 unmapped-table tests
# ─────────────────────────────────────────────────────────────────────────────

def test_unmapped_table_requires_audit_internal_key(tmp_path):
    """Unmapped-table row with audit_value but NO audit_internal_key
    should be skipped (we don't know which uni_account to write to)."""
    md = _write(tmp_path, [
        UNMAPPED_HEADER, UNMAPPED_SEP,
        "| Q1_FY2020 | Some weird label | 42 | USD_millions |  | 43 | note |",
    ])
    audits = apply_audit.parse_review_md(md, {})
    assert audits == []


def test_unmapped_table_with_audit_internal_key_emitted(tmp_path):
    md = _write(tmp_path, [
        UNMAPPED_HEADER, UNMAPPED_SEP,
        "| Q1_FY2020 | Some weird label | 42 | USD_millions | `adj_other` | 43 | x |",
    ])
    audits = apply_audit.parse_review_md(md, {})
    assert len(audits) == 1
    a = audits[0]
    assert a["internal_key"] == "adj_other"
    assert a["display_label"] == "Some weird label"
    assert a["audit_value"] == 43
    assert a["unit"] == "USD_millions"


# ─────────────────────────────────────────────────────────────────────────────
# F6 mixed tables in one file
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# F11: is_audit_value_filled header-aware
# ─────────────────────────────────────────────────────────────────────────────

def _import_extract_8k():
    """Lazy import — needs CC_Switch_Config skill path on sys.path."""
    sys.path.insert(
        0,
        "/Users/mensch5566/CC_Switch_Config/skills/parse-8k-nongaap/scripts",
    )
    import extract_8k_nongaap as e
    return e


def test_is_audit_value_filled_empty_audit_value_returns_false(tmp_path):
    """F11 core bug: NLM Non-GAAP numbers were being counted as filled."""
    e = _import_extract_8k()
    md = _write(tmp_path, [
        MAIN_HEADER, MAIN_SEP,
        "| Q1_FY2020 | Gross profit | `gross_profit` | HARD | 206.1 |  |  |  | $ millions |",
        "| Q1_FY2020 | Adj. EPS | `adj_eps` | HARD | 0.45 |  |  |  | USD_per_share |",
    ])
    assert e.is_audit_value_filled(md) is False


def test_is_audit_value_filled_filled_returns_true(tmp_path):
    e = _import_extract_8k()
    md = _write(tmp_path, [
        MAIN_HEADER, MAIN_SEP,
        "| Q1_FY2020 | Adj. EPS | `adj_eps` | HARD | 0.45 |  | 0.48 | corrected | USD_per_share |",
    ])
    assert e.is_audit_value_filled(md) is True


def test_is_audit_value_filled_mixed(tmp_path):
    e = _import_extract_8k()
    md = _write(tmp_path, [
        MAIN_HEADER, MAIN_SEP,
        "| Q1_FY2020 | Revenue | `revenue` | HARD | 500 |  |  |  | USD_millions |",
        "| Q1_FY2020 | Adj. EPS | `adj_eps` | HARD | 0.45 |  | 0.48 | x | USD_per_share |",
    ])
    assert e.is_audit_value_filled(md) is True


def test_is_audit_value_filled_unmapped_table(tmp_path):
    """Unmapped table also has audit_value column — must check both tables."""
    e = _import_extract_8k()
    md = _write(tmp_path, [
        UNMAPPED_HEADER, UNMAPPED_SEP,
        "| Q1_FY2020 | Weird | 42 | USD_millions | `adj_other` | 43 | x |",
    ])
    assert e.is_audit_value_filled(md) is True


def test_is_audit_value_filled_no_table_returns_false(tmp_path):
    e = _import_extract_8k()
    md = _write(tmp_path, ["# Header", "Some text", ""])
    assert e.is_audit_value_filled(md) is False


# ─────────────────────────────────────────────────────────────────────────────
# F12-R4-1 + R5-F2: 8-K extract resolve_8k_unit promoted to module-level for
# direct testing. R5-F1: USD_billions propagates (no down-convert).
# ─────────────────────────────────────────────────────────────────────────────

def test_resolve_8k_unit_dollar_thousands_canonicalizes():
    """F12-R4-1 core: `$ thousands` MUST NOT be silently mapped to USD_millions
    (old `$`-substring bug → 1000x scale error). Now → USD_thousands."""
    e = _import_extract_8k()
    assert e.resolve_8k_unit("$ thousands")      == "USD_thousands"
    assert e.resolve_8k_unit("thousands of USD") == "USD_thousands"


def test_resolve_8k_unit_dollar_millions_canonicalizes():
    e = _import_extract_8k()
    assert e.resolve_8k_unit("$ millions")      == "USD_millions"
    assert e.resolve_8k_unit("millions of USD") == "USD_millions"


def test_resolve_8k_unit_billions_propagates_no_downconvert():
    """R5-F1: USD_billions must propagate as-is, NOT be silently
    down-converted to USD_millions (that would change the unit string
    without scaling the value → reverse 1000x scale error)."""
    e = _import_extract_8k()
    assert e.resolve_8k_unit("billions of USD") == "USD_billions"
    assert e.resolve_8k_unit("$ billions")      == "USD_billions"


def test_resolve_8k_unit_percent():
    e = _import_extract_8k()
    assert e.resolve_8k_unit("%")       == "pct"
    assert e.resolve_8k_unit("percent") == "pct"


def test_resolve_8k_unit_per_share():
    e = _import_extract_8k()
    assert e.resolve_8k_unit("$ per share") == "USD_per_share"
    assert e.resolve_8k_unit("USD/share")   == "USD_per_share"


def test_resolve_8k_unit_empty_or_none_defaults_to_usd_millions():
    """Legacy fallback for missing unit (backward compat)."""
    e = _import_extract_8k()
    assert e.resolve_8k_unit("")   == "USD_millions"
    assert e.resolve_8k_unit(None) == "USD_millions"


def test_resolve_8k_unit_unknown_passthrough():
    """Unknown unit strings preserved as-is (legacy fallback)."""
    e = _import_extract_8k()
    assert e.resolve_8k_unit("widgets") == "widgets"



def test_main_and_unmapped_tables_both_parsed(tmp_path):
    md = _write(tmp_path, [
        "# Header",
        "",
        MAIN_HEADER, MAIN_SEP,
        "| Q1_FY2020 | Adj. EPS | `adj_eps` | HARD | 0.45 |  | 0.48 | x | USD_per_share |",
        "",
        "## Unmapped",
        "",
        UNMAPPED_HEADER, UNMAPPED_SEP,
        "| Q2_FY2020 | Weird | 1.0 | USD_millions | `adj_other` | 1.1 | y |",
    ])
    audits = apply_audit.parse_review_md(md, {})
    assert len(audits) == 2
    by_key = {a["internal_key"]: a for a in audits}
    assert by_key["adj_eps"]["audit_value"] == 0.48
    assert by_key["adj_other"]["audit_value"] == 1.1
