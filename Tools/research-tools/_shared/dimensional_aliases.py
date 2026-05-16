"""Member / axis label normalization for dimensional facts dedupe.

Spec: tmp/financials-viewer-redesign-plan.md §20.4 (v5.1).

Why: same XBRL member can be reported with label variants across filings
(e.g. AAOI segment "Data Center" in 10-Q vs "Datacenter" in 8-K). Without
normalization the dedupe key treats them as two members, breaking aggregate
verification.

Resolution rules:
    member_key = member_qname  if qname available (XBRL primary path)
               | "local:" + normalize_member_label(label)  if NLM fallback / no qname

normalize_member_label() pipeline:
    1. NFKC unicode normalize
    2. trim + lower
    3. strip trailing " Member" / " [Member]" / "(Member)"
    4. drop punctuation
    5. collapse whitespace
    6. apply MEMBER_ALIAS_MAP (canonical key lookup)

Adding new alias: edit MEMBER_ALIAS_MAP in this file, commit through code
review. Avoid per-ticker overrides until cross-ticker conflict appears
(then add an override layer in a separate module).
"""
from __future__ import annotations

import re
import unicodedata

# Canonical member alias map. Key = normalized label. Value = canonical key.
# Both sides should already be lower-cased / punctuation-stripped.
MEMBER_ALIAS_MAP: dict[str, str] = {
    # Product axis
    "datacenter": "data_center",
    "data center": "data_center",
    "data-center": "data_center",
    # geography
    "united states": "united_states",
    "u s": "united_states",
    "us": "united_states",
    "china": "china",
    "prc": "china",
    "taiwan": "taiwan",
    "republic of china": "taiwan",
    # network / telecom
    "ftth": "ftth",
    "ftth and other": "ftth_and_other",  # IMPORTANT: distinct member
    "catv": "catv",
    "telecom": "telecom",
    "5g": "5g",
    "fttx": "fttx",
}


_PUNCT_RE = re.compile(r"[^\w\s]")
_WS_RE = re.compile(r"\s+")
_TRAILING_MEMBER_RE = re.compile(r"\bmember\b\s*$")


def normalize_member_label(label: str) -> str:
    """Normalize a raw PDF / XBRL member label to a stable key.

    Returns a snake_case-like string. Never returns empty (raises on empty
    input so caller writes validation error).
    """
    if not label or not label.strip():
        raise ValueError("normalize_member_label: empty label")
    s = unicodedata.normalize("NFKC", label).strip().lower()
    # Strip [Member] / (Member) markers via punctuation removal first
    s = _PUNCT_RE.sub(" ", s)
    s = _WS_RE.sub(" ", s).strip()
    # Strip trailing standalone "member" word
    s = _TRAILING_MEMBER_RE.sub("", s).strip()
    s = _WS_RE.sub(" ", s).strip()
    # Alias lookup (allow either spaced or underscored canonical form)
    if s in MEMBER_ALIAS_MAP:
        return MEMBER_ALIAS_MAP[s]
    # Default: underscore-join
    return s.replace(" ", "_") or "unknown"


def normalize_axis_label(axis: str) -> str:
    if not axis or not axis.strip():
        raise ValueError("normalize_axis_label: empty axis")
    s = unicodedata.normalize("NFKC", axis).strip().lower()
    return re.sub(r"[^\w]+", "_", s).strip("_")


def build_axis_key(axis: str, axis_qname: str | None) -> str:
    """axis_key = axis_qname (preferred) | "local:" + normalize_axis_label(axis)."""
    if axis_qname and axis_qname.strip():
        return axis_qname.strip()
    return f"local:{normalize_axis_label(axis)}"


def build_member_key(member: str, member_qname: str | None) -> str:
    """member_key = member_qname (preferred) | "local:" + normalize_member_label(member)."""
    if member_qname and member_qname.strip():
        return member_qname.strip()
    return f"local:{normalize_member_label(member)}"
