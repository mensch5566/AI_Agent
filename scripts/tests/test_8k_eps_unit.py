"""Regression: EPS Non-GAAP rows must always resolve to USD_per_share.

Root cause (LITE Non-GAAP EPS rendered "2"): NLM inherits the reconciliation
table header ("in millions, except per share data") and labels the EPS row's
`unit` as millions / bare USD. The downstream money formatter then rounds the
per-share value to an integer. EPS is *definitionally* per-share, so the unit
must be overridden by uni_account regardless of NLM's contaminated label.

Cross-ticker symptom this locks down: GLW=USD_per_share, MU=USD,
LITE/SNDK=USD_millions for the same eps_diluted concept.
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

import extract_8k_nongaap as e8k  # noqa: E402


# ── EPS keys: any header-contaminated unit collapses to USD_per_share ────────
def test_eps_diluted_millions_header_becomes_per_share():
    # LITE / SNDK symptom: "$ millions" header bleeds onto the EPS row.
    assert e8k.resolve_8k_row_unit("eps_diluted", "$ millions") == "USD_per_share"
    assert e8k.resolve_8k_row_unit("eps_diluted", "millions") == "USD_per_share"


def test_eps_bare_usd_becomes_per_share():
    # MU symptom: NLM returns bare "USD" / "$".
    assert e8k.resolve_8k_row_unit("eps_diluted", "USD") == "USD_per_share"
    assert e8k.resolve_8k_row_unit("eps_diluted", "$") == "USD_per_share"


def test_eps_basic_explicit_per_share_unchanged():
    # GLW symptom (already correct) stays correct.
    assert e8k.resolve_8k_row_unit("eps_basic", "per share") == "USD_per_share"
    assert e8k.resolve_8k_row_unit("eps_basic", "USD_per_share") == "USD_per_share"


def test_eps_empty_unit_defaults_per_share():
    assert e8k.resolve_8k_row_unit("eps_diluted", "") == "USD_per_share"
    assert e8k.resolve_8k_row_unit("eps_basic", None) == "USD_per_share"


# ── Non-EPS keys: behavior preserved (no per-share override) ─────────────────
def test_revenue_millions_stays_millions():
    assert e8k.resolve_8k_row_unit("revenue", "$ millions") == "USD_millions"


def test_revenue_bare_dollar_infers_millions():
    # Legacy bare-'$' inference for non-EPS rows must be retained.
    assert e8k.resolve_8k_row_unit("revenue", "$") == "USD_millions"


def test_shares_diluted_not_per_share():
    # Weighted-average share count is NOT per-share — must not be overridden.
    assert e8k.resolve_8k_row_unit("shares_diluted_millions", "millions") == "USD_millions"


def test_unmapped_key_none_keeps_resolved_unit():
    # key=None (unmapped, pre-LLM) must not crash and keeps resolved unit.
    assert e8k.resolve_8k_row_unit(None, "$ millions") == "USD_millions"
    assert e8k.resolve_8k_row_unit(None, "$") == "USD_millions"
