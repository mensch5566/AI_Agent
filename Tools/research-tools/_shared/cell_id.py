"""Deterministic cell_id / edge_id hash for sec_financial_* tables.

Spec: tmp/financials-viewer-redesign-plan.md §16.4 (v4) + §18.4 (v5) + §20.4 (v5.1).

All identity hashes use SHA-256 truncated to 32 hex chars (128-bit collision
space, sufficient for cross-ticker uniqueness with margin).

Input order, casing, and null sentinels are fixed and MUST NOT change without
a coordinated migration. Upsert script, API layer, and future derive scripts
all import from this module — one canonical implementation.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any


def _h(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:32]


def _norm(v: Any) -> str:
    """Null sentinel: None / empty string -> ''. Strings preserved as-is."""
    if v is None:
        return ""
    return str(v)


def canonical_json(obj: Any) -> str:
    """Stable JSON for cell_id input.

    - Keys sorted alphabetically.
    - No whitespace.
    - None values -> null.
    - Empty list -> "[]".
    """
    if obj is None:
        return "[]"
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def facts_cell_id(
    *,
    ticker: str,
    period: str,
    period_kind: str,
    version: str,
    statement: str,
    uni_account: str,
    source_account: str,
    xbrl_tag: str | None = None,
) -> str:
    """Identity for sec_financial_facts row.

    MUST stay in sync with sff_identity unique index in migration.
    """
    parts = [
        "facts",
        ticker.upper(),
        period,
        period_kind,
        version,
        statement,
        uni_account,
        _norm(source_account),
        _norm(xbrl_tag),
    ]
    return _h("|".join(parts))


def metrics_cell_id(
    *,
    ticker: str,
    period: str,
    period_kind: str,
    version: str,
    statement: str,
    uni_account: str,
) -> str:
    """Identity for sec_financial_metrics row.

    No source_account (derived metrics have no PDF label).
    """
    parts = [
        "metrics",
        ticker.upper(),
        period,
        period_kind,
        version,
        statement,
        uni_account,
    ]
    return _h("|".join(parts))


def dimensional_cell_id(
    *,
    ticker: str,
    period: str,
    period_kind: str,
    axis_key: str,
    member_key: str,
    uni_account: str,
    other_dimensions: list[dict] | None = None,
) -> str:
    """Identity for sec_financial_dimensional_facts row.

    Uses axis_key / member_key (qname or normalized label) — see
    dimensional_aliases.build_axis_key / build_member_key.

    source_doc and raw labels do NOT participate in identity (multi-source
    dedupe collapses to one row with provenance.sources[] preserving variants).
    """
    parts = [
        "dimensional",
        ticker.upper(),
        period,
        period_kind,
        axis_key,
        member_key,
        uni_account,
        canonical_json(other_dimensions),
    ]
    return _h("|".join(parts))


def edge_id(
    *,
    ticker: str,
    period: str,
    edge_type: str,
    role_uri: str,
    parent_qname: str | None,
    child_qname: str,
    preferred_label: str | None = None,
    ordinal: float | None = None,
) -> str:
    """Identity for sec_financial_edges row.

    `preferred_label` + `ordinal` are included because the same parent-child
    pair can legitimately appear multiple times in the same presentation role
    with different label roles (e.g. periodStartLabel vs periodEndLabel) and
    different positional ordinals (XBRL allows this for instant facts).
    """
    parts = [
        "edge",
        ticker.upper(),
        period,
        edge_type,
        role_uri,
        _norm(parent_qname),
        child_qname,
        _norm(preferred_label),
        _norm(ordinal),
    ]
    return _h("|".join(parts))
