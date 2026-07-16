"""Upsert TWSE (Taiwan) v2 financials → the SHARED Supabase tables (Phase E storage).

Spec: docs/superpowers/specs/2026-07-05-phase-e-tw-frontend-design.md §3 E1, §1.

TW twin of scripts/upsert_sec_financials.py — mirrors its dry-run/`--apply`,
freshness gate, snapshot-replace, and facts-wins mechanisms verbatim, but for the
Taiwan pipeline. Differences (spec §3 E1):

  * Path: MOPS Filings (not SEC Filings). The vault folder is the Chinese COMPANY
    NAME (聯亞), not the ticker (3081) — discovered by globbing for the folder that
    holds parse-twse-ixbrl/{ticker}_twse_facts.json. Fail-loud on 0 or >1 hits.
  * Sources: twse facts (adapt_company_twse / adapt_twse_facts) + derive-base
    metrics + derive-analytics metrics. NO nongaap, NO supplement, NO dimensional,
    NO edges (the TW pipeline produces none of these).
  * exchange=TWSE / currency=TWD (self-describing discriminators — no market column,
    Option 2, zero migration).

Storage: the SAME market-agnostic tables the US pipeline uses:
  sec_financial_companies / sec_financial_facts / sec_financial_metrics.

Usage:
    # dry-run 3081 (default — NEVER touches DB)
    python3 scripts/upsert_twse_financials.py 3081

    # real upsert (requires explicit human authorization)
    python3 scripts/upsert_twse_financials.py 3081 --apply

Skill output is expected under (folder = Chinese company name, discovered by glob):
    Obsidian/Khouse/Semiconductors/{COMPANY_NAME}/01_Source/MOPS Filings/Skill_Output/
        parse-twse-ixbrl/{TICKER}_twse_facts.json
        derive-base/{run}/{TICKER}_derived.json
        derive-analytics/{run}/{TICKER}_analytics.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "Tools" / "research-tools"))

from _shared import twse_json_adapter as TW  # noqa: E402
from _shared.twse_canonical_facts import adapt_twse_canonical_facts  # noqa: E402
from _shared.sec_json_adapter import NormalizedBatch  # noqa: E402

OBSIDIAN_BASE = Path(os.environ.get(
    "OBSIDIAN_VAULT",
    os.path.expanduser("~/Obsidian"),
))

BATCH_SIZE = 500

# MOPS Filings glob (the TW analogue of the SEC Filings path). The company folder
# is the Chinese company name, so we glob every Semiconductors/* and pick the one
# holding this ticker's twse facts (proven pattern: compose-financials loaders
# `_ticker_base` tw branch).
MOPS_SKILL_OUTPUT = "01_Source/MOPS Filings/Skill_Output"


# Authoritative list of all derive-base rule_ids the TW (market-agnostic) pipeline
# has EVER produced. Used for (a) missing_run gate scope, (b) snapshot-replacement
# delete scope. Superset of the SEC list + TW-specific IDENTITY / EPS rules so a
# rule that stops firing in a later run still has its orphan rows cleared. Keep in
# sync with the derive-base skill's rule registry.
DERIVE_BASE_RULE_IDS_FALLBACK = (
    # Q2 / Q3 / Q4 single-quarter reconstruction from disclosed YTD.
    "Q2_6M_MINUS_Q1",
    "Q3_9M_MINUS_6M",
    "Q4_FY_MINUS_9M",
    "Q4_FY_MINUS_Q1Q2Q3",
    "Q4_EPS_APPROX_FY_MINUS_Q1Q2Q3",
    # Identity rules (TW derive-base emits IDENTITY_DA_DEP_PLUS_AMORT for 3081).
    "IDENTITY_DA_DEP_PLUS_AMORT",
    "IDENTITY_IBT_FROM_OP_PLUS_NONOP",
    "IDENTITY_IBT_FROM_OP_MINUS_INTEXP_PLUS_NONOP",
    # XBRL calculation linkbase derivation + allowlists (shared engine).
    "CALC_LINKBASE",
    "STATIC_ALLOWLIST",
    "NG_ALLOWLIST",
)

# Owned rule registry for derive-analytics (shared market-agnostic engine). Mirrors
# the derive-analytics skill registry (68 rules = 24 non-growth + 44 growth) so the
# analytics snapshot delete scope covers every rule the skill can emit — including
# the QoQ/YoY rules the TW pipeline emits. Keep in sync with rules_ratios.ALL_RULE_IDS
# ∪ rules_crossperiod.ALL_CROSSPERIOD_RULE_IDS.
DERIVE_ANALYTICS_RULE_IDS_FALLBACK = (
    "RATIO_GROSS_MARGIN_PCT",
    "RATIO_OPERATING_MARGIN_PCT",
    "RATIO_NET_MARGIN_PCT",
    "RATIO_EFFECTIVE_TAX_RATE",
    "RATIO_CURRENT_RATIO",
    "RATIO_CASH_RATIO",
    "RATIO_QUICK_RATIO",
    "RATIO_DEBT_TO_EQUITY",
    "RATIO_INTEREST_COVERAGE",
    "RATIO_FCF_MARGIN_PCT",
    "FCF_CFO_MINUS_CAPEX",
    "EBITDA_NI_INT_TAX_DA",
    "RATIO_EBITDA_MARGIN_PCT",
    "RATIO_ADJUSTED_EBITDA_MARGIN_PCT",
    "RATIO_BVPS",
    "RATIO_ROE",
    "RATIO_ROA",
    "RATIO_ASSET_TURNOVER",
    "RATIO_DIO",
    "RATIO_DSO",
    "RATIO_DPO",
    "RATIO_CCC",
    "RATIO_ROIC",
    "RATIO_NET_DEBT_TO_EBITDA",
    # Rate-of-change growth family: 22 IS metrics × {qoq,yoy} = 44. TW pipeline
    # emits the full set. Keep in sync with rules_crossperiod.GROWTH_RULES.
    "RATIO_REVENUE_QOQ",
    "RATIO_REVENUE_YOY",
    "RATIO_GROSS_PROFIT_QOQ",
    "RATIO_GROSS_PROFIT_YOY",
    "RATIO_OPERATING_INCOME_QOQ",
    "RATIO_OPERATING_INCOME_YOY",
    "RATIO_NET_INCOME_QOQ",
    "RATIO_NET_INCOME_YOY",
    "RATIO_EPS_DILUTED_QOQ",
    "RATIO_EPS_DILUTED_YOY",
    "RATIO_COST_OF_GOODS_SOLD_QOQ",
    "RATIO_COST_OF_GOODS_SOLD_YOY",
    "RATIO_INCOME_BEFORE_TAXES_QOQ",
    "RATIO_INCOME_BEFORE_TAXES_YOY",
    "RATIO_INCOME_TAX_EXPENSE_QOQ",
    "RATIO_INCOME_TAX_EXPENSE_YOY",
    "RATIO_EPS_BASIC_QOQ",
    "RATIO_EPS_BASIC_YOY",
    "RATIO_SELLING_EXPENSES_QOQ",
    "RATIO_SELLING_EXPENSES_YOY",
    "RATIO_GENERAL_ADMIN_EXPENSES_QOQ",
    "RATIO_GENERAL_ADMIN_EXPENSES_YOY",
    "RATIO_RESEARCH_AND_DEVELOPMENT_QOQ",
    "RATIO_RESEARCH_AND_DEVELOPMENT_YOY",
    "RATIO_EXPECTED_CREDIT_LOSS_QOQ",
    "RATIO_EXPECTED_CREDIT_LOSS_YOY",
    "RATIO_TOTAL_OPERATING_EXPENSES_QOQ",
    "RATIO_TOTAL_OPERATING_EXPENSES_YOY",
    "RATIO_SELLING_GENERAL_ADMINISTRATIVE_QOQ",
    "RATIO_SELLING_GENERAL_ADMINISTRATIVE_YOY",
    "RATIO_INTEREST_INCOME_QOQ",
    "RATIO_INTEREST_INCOME_YOY",
    "RATIO_INTEREST_EXPENSE_QOQ",
    "RATIO_INTEREST_EXPENSE_YOY",
    "RATIO_OTHER_GAINS_LOSSES_QOQ",
    "RATIO_OTHER_GAINS_LOSSES_YOY",
    "RATIO_NON_OPERATING_INCOME_EXPENSE_QOQ",
    "RATIO_NON_OPERATING_INCOME_EXPENSE_YOY",
    "RATIO_OTHER_NONOPERATING_INCOME_EXPENSE_QOQ",
    "RATIO_OTHER_NONOPERATING_INCOME_EXPENSE_YOY",
    "RATIO_NET_INCOME_TOTAL_PRE_NCI_QOQ",
    "RATIO_NET_INCOME_TOTAL_PRE_NCI_YOY",
    "RATIO_NET_INCOME_NCI_QOQ",
    "RATIO_NET_INCOME_NCI_YOY",
    # Share-structure adjustment (ADJ) ids — Class-A-rebased EPS/shares level rows
    # (emitted by adjustment.py, not an AnalyticsRule) + their qoq/yoy growth rows.
    "ADJ_EPS_BASIC",
    "ADJ_EPS_DILUTED",
    "ADJ_COMMON_SHARES_OUTSTANDING",
    "ADJ_FACTOR_CUM",
    "RATIO_EPS_BASIC_ADJ_YOY",
    "RATIO_EPS_BASIC_ADJ_QOQ",
    "RATIO_EPS_DILUTED_ADJ_YOY",
    "RATIO_EPS_DILUTED_ADJ_QOQ",
)


def analytics_delete_scope(payload_managed_rule_ids) -> list[str]:
    """Delete scope for derive-analytics snapshot replacement (union of the
    payload's self-declared managed_rule_ids with the owned registry fallback)."""
    return sorted(
        set(payload_managed_rule_ids or ()) | set(DERIVE_ANALYTICS_RULE_IDS_FALLBACK)
    )


def derive_base_delete_scope(payload_managed_rule_ids) -> list[str]:
    """Delete scope for derive-base snapshot replacement (symmetric with
    analytics_delete_scope)."""
    return sorted(
        set(payload_managed_rule_ids or ()) | set(DERIVE_BASE_RULE_IDS_FALLBACK)
    )


# ---- Folder discovery (glob) -------------------------------------------------


def discover_tw_base(vault: Path, ticker: str) -> Path:
    """Discover the Skill_Output base for a TW ticker.

    The vault folder is the Chinese company name (聯亞), not the ticker, so we glob
    every Semiconductors/*/MOPS Filings/Skill_Output and keep the one(s) holding
    parse-twse-ixbrl/{ticker}_twse_facts.json. Fail-loud (SystemExit) on 0 hits
    (not onboarded) or >1 hits (ambiguous — two folders claim the same ticker)."""
    hits = []
    for cand in sorted(Path(vault).glob(f"Khouse/Semiconductors/*/{MOPS_SKILL_OUTPUT}")):
        if (cand / "parse-twse-ixbrl" / f"{ticker}_twse_facts.json").is_file():
            hits.append(cand)
    if not hits:
        raise SystemExit(
            f"No TWSE facts found for {ticker} under "
            f"Khouse/Semiconductors/*/{MOPS_SKILL_OUTPUT}/parse-twse-ixbrl/. "
            f"Run parse-twse-ixbrl first."
        )
    if len(hits) > 1:
        listing = "\n    ".join(str(h) for h in hits)
        raise SystemExit(
            f"Ambiguous: {len(hits)} company folders contain "
            f"{ticker}_twse_facts.json — resolve before upsert:\n    {listing}"
        )
    return hits[0]


# ---- IO helpers --------------------------------------------------------------


def load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def latest_run_json_path(base: Path, skill_dir: str, json_filename: str):
    """Path to the CURRENT latest run's JSON for a skill, or None if absent."""
    parent = base / skill_dir
    if not parent.exists():
        return None
    runs = sorted(p for p in parent.iterdir() if p.is_dir())
    if not runs:
        return None
    p = runs[-1] / json_filename
    return p if p.exists() else None


# ---- Pipeline (normalize) ----------------------------------------------------


def normalize(ticker: str, base: Path) -> NormalizedBatch:
    """Load twse facts under `base` and adapt → NormalizedBatch.

    TW-only: company + facts. No nongaap / supplement / dimensional / edges.
    """
    facts_path = base / "parse-twse-ixbrl" / f"{ticker}_twse_facts.json"
    facts_json = load_json(facts_path)
    if facts_json is None:
        raise SystemExit(
            f"TWSE facts missing for {ticker} at {facts_path} — run parse-twse-ixbrl first")

    batch = NormalizedBatch(ticker=ticker)
    batch.company = TW.adapt_company_twse(facts_json)
    # DB facts layer must be AS-REPORTED (capex negative, cash balances present) —
    # NOT the derive adapter (TW.adapt_twse_facts), which flips capex + drops cash
    # balances for the derive engine. See twse_canonical_facts docstring.
    batch.facts.extend(adapt_twse_canonical_facts(facts_json))
    return batch


# ---- Report (dry-run / real-run) --------------------------------------------


def print_report(batch: NormalizedBatch) -> bool:
    """Print dry-run / real-run report. Return True if gate passes."""
    print(f"\n=== {batch.ticker} TWSE normalization report ===")
    print(f"  company: {batch.company.company_name} ({batch.company.exchange}) "
          f"currency={batch.company.currency} cik={batch.company.cik!r}")

    fact_by_stmt = Counter(r.statement for r in batch.facts)
    fact_by_ver = Counter(r.version for r in batch.facts)
    print(f"\n  facts: {len(batch.facts)} rows")
    print(f"    by statement: {dict(fact_by_stmt)}")
    print(f"    by version: {dict(fact_by_ver)}")
    print(f"    by period_kind: {dict(Counter(r.period_kind for r in batch.facts))}")
    print(f"    by unit: {dict(Counter(r.unit for r in batch.facts))}")

    # Identity uniqueness
    fact_ids = [r.cell_id for r in batch.facts]
    fact_dup = len(fact_ids) - len(set(fact_ids))
    print(f"\n  identity uniqueness:")
    print(f"    facts: {len(set(fact_ids))}/{len(fact_ids)} unique (dup={fact_dup})")

    gate_pass = True
    print(f"\n  === Open Gate ===")
    checks = [
        ("rejected rows = 0", len(batch.rejected) == 0, f"rejected={len(batch.rejected)}"),
        ("facts identity unique", fact_dup == 0, f"dup={fact_dup}"),
        ("facts present", len(batch.facts) > 0, f"n={len(batch.facts)}"),
    ]
    for name, ok, detail in checks:
        mark = "✓" if ok else "✗"
        print(f"    [{mark}] {name} ({detail})")
        if not ok:
            gate_pass = False

    if batch.rejected:
        print(f"\n  rejected rows (first 5):")
        for r in batch.rejected[:5]:
            print(f"    {r}")

    return gate_pass


# ---- Supabase upsert (real-run only) ----------------------------------------


def supabase_client():
    """Lazy import + env load."""
    env = {}
    env_path = REPO_ROOT / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    env[k] = v
    url = env.get("NEXT_PUBLIC_SUPABASE_URL") or env.get("SUPABASE_URL")
    key = env.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise SystemExit("Missing NEXT_PUBLIC_SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY in .env")
    from supabase import create_client
    return create_client(url, key)


def upsert_batch(client, table: str, rows: list[dict]) -> int:
    if not rows:
        return 0
    total = 0
    for i in range(0, len(rows), BATCH_SIZE):
        chunk = rows[i : i + BATCH_SIZE]
        client.table(table).upsert(chunk).execute()
        total += len(chunk)
    return total


def row_to_dict(row) -> dict:
    """asdict + JSON-friendly fixups for FactRow.

    `display_eligible` is an adapter-internal flag with no DB column — stripped.
    `ordinal` (TW facts always None) is smallint; coerce integer-valued floats.
    """
    d = asdict(row)
    d.pop("display_eligible", None)
    if "ordinal" in d:
        d["ordinal"] = _coerce_ordinal(d["ordinal"])
    return d


def _coerce_ordinal(ordinal):
    if ordinal is None:
        return None
    f = float(ordinal)
    if f != int(f):
        raise ValueError(
            f"non-integer ordinal {ordinal!r} cannot be stored in smallint column "
            f"without truncation/collision.")
    return int(f)


def apply(batch: NormalizedBatch) -> None:
    client = supabase_client()

    # 1. companies
    company_row = {
        "ticker": batch.company.ticker,
        "company_name": batch.company.company_name,
        "exchange": batch.company.exchange,
        "cik": batch.company.cik,
        "currency": batch.company.currency,
        "fiscal_year_end_month": batch.company.fiscal_year_end_month,
        "filings": batch.company.filings,
        "sign_flip_concepts": batch.company.sign_flip_concepts,
    }
    client.table("sec_financial_companies").upsert(company_row).execute()
    print(f"  upserted: sec_financial_companies (1 row)")

    # 2. facts
    n = upsert_batch(client, "sec_financial_facts", [row_to_dict(r) for r in batch.facts])
    print(f"  upserted: sec_financial_facts ({n} rows)")

    # TW pipeline has NO dimensional / edges — nothing else to write here.


# ---- Derived metrics (derive-base / derive-analytics output) -----------------


def load_derived_metrics(base: Path, ticker: str) -> tuple[str, list[dict]]:
    """(status, rows) — derived_metrics from the latest derive-base run."""
    status, payload = load_derived_run(base, ticker)
    return status, (payload.get("derived_metrics", []) if payload else [])


def load_derived_run(base: Path, ticker: str) -> tuple[str, dict | None]:
    """Latest derive-base run for `ticker`. Tri-state (status, payload):
      - ("missing_run", None)     — no derive-base dir / no runs
      - ("incomplete_run", None)  — run folder exists but JSON missing/unparseable
      - ("loaded", payload_dict)  — JSON loaded (derived_metrics may be [])
    """
    return _load_skill_run(base, "derive-base", f"{ticker}_derived.json", "derived_metrics")


def load_analytics_run(base: Path, ticker: str) -> tuple[str, dict | None]:
    """Latest derive-analytics run for `ticker`. Same tri-state as
    load_derived_run. Rows under canonical `analytics_metrics` (legacy
    `ratio_metrics` accepted defensively)."""
    return _load_skill_run(base, "derive-analytics", f"{ticker}_analytics.json",
                           ("analytics_metrics", "ratio_metrics"))


def _load_skill_run(base: Path, skill_dir: str, json_filename: str,
                    rows_key) -> tuple[str, dict | None]:
    parent = base / skill_dir
    if not parent.exists():
        return ("missing_run", None)
    runs = sorted(p for p in parent.iterdir() if p.is_dir())
    if not runs:
        return ("missing_run", None)
    payload_path = runs[-1] / json_filename
    if not payload_path.exists():
        return ("incomplete_run", None)
    try:
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ("incomplete_run", None)
    keys = (rows_key,) if isinstance(rows_key, str) else tuple(rows_key)
    if all(payload.get(k) is None for k in keys):
        return ("incomplete_run", None)
    return ("loaded", payload)


# R7-F1: minimum input_files contract a TW derive-base run must carry. The TW
# derive skills record `twse_facts` (not the SEC gaap_* keys) as their source.
_REQUIRED_INPUT_FILE_KEYS = frozenset({"twse_facts"})


def analytics_required_keys(derive_status: str) -> set:
    """Minimum input_files lineage the analytics freshness gate must require.

    derive-analytics consumes twse facts + derive-base. When derive-base is
    loaded, the analytics run MUST have consulted it (require `derive_base`),
    else raw-only ratios would ship next to fresh derive-base metrics.
    """
    keys = {"twse_facts"}
    if derive_status == "loaded":
        keys.add("derive_base")
    return keys


def analytics_derive_base_is_current(analytics_payload: dict, latest_db_json_path) -> bool:
    """True if the analytics run consumed the CURRENT latest derive-base run
    (path-version drift guard the freshness hash alone misses)."""
    if latest_db_json_path is None:
        return True
    info = ((analytics_payload or {}).get("metadata", {}) or {}).get("input_files", {}) or {}
    db = info.get("derive_base")
    if not isinstance(db, dict) or not db.get("path"):
        return False
    return Path(db["path"]).resolve() == Path(latest_db_json_path).resolve()


def verify_derived_freshness(payload: dict, required_keys=None) -> list[dict]:
    """Re-hash every source in payload.metadata.input_files vs stored sha256.
    Returns mismatch descriptors (empty = fresh). Mirrors the SEC gate, but the
    default required-key contract is the TW `twse_facts` key."""
    import hashlib
    if required_keys is None:
        required_keys = _REQUIRED_INPUT_FILE_KEYS
    metadata = (payload or {}).get("metadata") or {}
    input_files = metadata.get("input_files")
    mismatches: list[dict] = []

    if not input_files:
        mismatches.append({
            "key": "(metadata.input_files)", "path": None,
            "stored_sha256": None, "current_sha256": None,
            "reason": "input_files_missing",
        })
        return mismatches
    for required_key in required_keys:
        if required_key not in input_files or input_files[required_key] is None:
            mismatches.append({
                "key": required_key, "path": None,
                "stored_sha256": None, "current_sha256": None,
                "reason": "input_file_key_missing",
            })

    for key, info in input_files.items():
        if info is None:
            continue
        if not isinstance(info, dict) or not info.get("path") or not info.get("sha256"):
            mismatches.append({
                "key": key, "path": (info.get("path") if isinstance(info, dict) else None),
                "stored_sha256": (info.get("sha256") if isinstance(info, dict) else None),
                "current_sha256": None,
                "reason": "input_file_metadata_invalid",
            })
            continue
        path = Path(info["path"])
        stored = info["sha256"]
        if not path.is_file():
            mismatches.append({
                "key": key, "path": str(path),
                "stored_sha256": stored, "current_sha256": None,
                "reason": "file_missing",
            })
            continue
        try:
            data = path.read_bytes()
        except OSError:
            mismatches.append({
                "key": key, "path": str(path),
                "stored_sha256": stored, "current_sha256": None,
                "reason": "file_unreadable",
            })
            continue
        current = hashlib.sha256(data).hexdigest()
        if current != stored:
            mismatches.append({
                "key": key, "path": str(path),
                "stored_sha256": stored, "current_sha256": current,
                "reason": "hash_mismatch",
            })
    return mismatches


# ---- facts-wins guard (storage boundary) ------------------------------------


def _ratio_logical_key(r) -> tuple:
    return (r.get("period"), r.get("period_kind"), r.get("version"),
            r.get("statement"), r.get("uni_account"))


def filter_derived_rows_against_facts(derived_rows, facts_logical_keys) -> list:
    """facts-wins at the STORAGE boundary: drop any derived metrics row whose
    logical identity collides with a disclosed sec_financial_facts row."""
    keys = set(facts_logical_keys)
    return [r for r in derived_rows if _ratio_logical_key(r) not in keys]


def fetch_facts_logical_keys(client, ticker: str, page: int = 1000) -> set:
    """Fetch ALL disclosed-facts logical keys for a ticker, paginating past
    Supabase's 1000-row cap, ordered by cell_id for a deterministic page
    boundary contract."""
    keys: set = set()
    frm = 0
    while True:
        res = (client.table("sec_financial_facts")
               .select("period,period_kind,version,statement,uni_account")
               .eq("ticker", ticker)
               .order("cell_id")
               .range(frm, frm + page - 1)
               .execute())
        rows = res.data or []
        for f in rows:
            keys.add(_ratio_logical_key(f))
        if len(rows) < page:
            break
        frm += page
    return keys


# ---- CLI ---------------------------------------------------------------------


def main():
    p = argparse.ArgumentParser()
    p.add_argument("ticker", help="TWSE ticker (4-digit, e.g. 3081)")
    p.add_argument("--apply", action="store_true",
                   help="real upsert to Supabase (default: dry-run)")
    p.add_argument("--allow-missing-derived", action="store_true",
                   help="Allow --apply when local derive output is missing AND "
                        "Supabase already has derive-managed metrics for this ticker. "
                        "Default fail-closed (prevents mixed-vintage state).")
    args = p.parse_args()
    ticker = str(args.ticker)  # TW tickers are numeric strings — do NOT upper()

    base = discover_tw_base(OBSIDIAN_BASE, ticker)
    print(f"  TW company folder: {base}")

    batch = normalize(ticker, base)
    gate_pass = print_report(batch)
    if not gate_pass:
        print("\n  ✗ Gate FAILED — refusing to upsert. Fix issues above and re-run.")
        sys.exit(1)

    # ---- derive-base status ----
    derive_status, derived_payload = load_derived_run(base, ticker)
    derived_rows = (derived_payload or {}).get("derived_metrics", []) if derived_payload else []
    if derive_status == "loaded":
        print(f"\n  + derive-base output: {len(derived_rows)} rows (status=loaded)")
    elif derive_status == "missing_run":
        print(f"\n  (no derive-base output found for {ticker})")
    elif derive_status == "incomplete_run":
        print(f"\n  ⚠ derive-base latest run INCOMPLETE for {ticker}")

    # ---- derive-analytics status (dry-run visibility) ----
    analytics_status_dry, analytics_payload_dry = load_analytics_run(base, ticker)
    analytics_rows_dry = []
    if analytics_status_dry == "loaded" and analytics_payload_dry:
        analytics_rows_dry = (analytics_payload_dry.get("analytics_metrics")
                              or analytics_payload_dry.get("ratio_metrics") or [])
        print(f"  + derive-analytics output: {len(analytics_rows_dry)} rows (status=loaded)")
    elif analytics_status_dry == "missing_run":
        print(f"  (no derive-analytics output found for {ticker})")
    elif analytics_status_dry == "incomplete_run":
        print(f"  ⚠ derive-analytics latest run INCOMPLETE for {ticker}")

    # ---- apply-path fail-closed gates (mirror SEC) ----
    if args.apply and derive_status == "incomplete_run":
        print(f"\n  ✗ Refusing --apply: derive-base latest run is incomplete for {ticker}.")
        sys.exit(2)

    if args.apply and derive_status == "missing_run" and not args.allow_missing_derived:
        client = supabase_client()
        existing = (client.table("sec_financial_metrics")
                    .select("cell_id", count="exact")
                    .eq("ticker", ticker)
                    .in_("provenance->>rule_id", list(DERIVE_BASE_RULE_IDS_FALLBACK))
                    .limit(1)
                    .execute())
        if existing.count and existing.count > 0:
            print(f"\n  ✗ Refusing --apply: derive-base output missing for {ticker} "
                  f"but Supabase has {existing.count} existing derive-base-managed rows.")
            print(f"     Run derive-base for {ticker} first, or pass --allow-missing-derived.")
            sys.exit(4)

    if args.apply and derive_status == "loaded" and derived_payload is not None:
        mismatches = verify_derived_freshness(derived_payload)
        if mismatches:
            print(f"\n  ✗ Refusing --apply: derive-base output is STALE for {ticker}.")
            for m in mismatches:
                print(f"       - {m['key']}: {m['reason']}")
            print(f"     Re-run derive-base for {ticker} and retry. Existing DB rows preserved.")
            sys.exit(3)

    # ---- derive-analytics apply-path gates ----
    if args.apply:
        _as, _ap = load_analytics_run(base, ticker)
        if _as == "incomplete_run":
            print(f"\n  ✗ Refusing --apply: derive-analytics latest run INCOMPLETE for {ticker}.")
            sys.exit(2)
        if _as == "missing_run" and not args.allow_missing_derived:
            client = supabase_client()
            existing = (client.table("sec_financial_metrics")
                        .select("cell_id", count="exact")
                        .eq("ticker", ticker)
                        .in_("provenance->>rule_id", list(DERIVE_ANALYTICS_RULE_IDS_FALLBACK))
                        .limit(1)
                        .execute())
            if existing.count and existing.count > 0:
                print(f"\n  ✗ Refusing --apply: derive-analytics output missing for {ticker} "
                      f"but Supabase has {existing.count} existing analytics-managed row(s).")
                print(f"     Run derive-analytics for {ticker} first, or pass --allow-missing-derived.")
                sys.exit(4)
        if _as == "loaded" and _ap is not None:
            a_mismatches = verify_derived_freshness(
                _ap, required_keys=analytics_required_keys(derive_status))
            if a_mismatches:
                print(f"\n  ✗ Refusing --apply: derive-analytics output is STALE for {ticker}.")
                for m in a_mismatches:
                    print(f"       - {m['key']}: {m['reason']}")
                print(f"     Re-run derive-analytics for {ticker} and retry. Existing DB rows preserved.")
                sys.exit(3)
            if derive_status == "loaded":
                latest_db = latest_run_json_path(base, "derive-base", f"{ticker}_derived.json")
                if not analytics_derive_base_is_current(_ap, latest_db):
                    print(f"\n  ✗ Refusing --apply: derive-analytics ran against an older "
                          f"derive-base run than the current latest for {ticker}.")
                    sys.exit(3)

    if args.apply:
        print(f"\n=== Real upsert to Supabase ===")
        client = None
        apply(batch)

        # ---- derive-base snapshot replacement ----
        if derive_status == "loaded":
            managed = (derived_payload.get("metadata", {}) or {}).get("managed_rule_ids") or []
            delete_scope = derive_base_delete_scope(managed)
            client = supabase_client()
            del_r = (client.table("sec_financial_metrics")
                     .delete()
                     .eq("ticker", ticker)
                     .in_("provenance->>rule_id", delete_scope)
                     .execute())
            print(f"  cleared derive-base scope ({len(delete_scope)} rule_ids, "
                  f"current managed={managed}): sec_financial_metrics "
                  f"({len(del_r.data)} rows deleted)")
            if derived_rows:
                client.table("sec_financial_metrics").upsert(
                    derived_rows, on_conflict="cell_id").execute()
                print(f"  upserted: sec_financial_metrics ({len(derived_rows)} derive-base rows)")
            else:
                print(f"  (derive-base loaded an intentionally empty set — derive scope now empty)")
        else:
            print(f"  ⚠ skipping derive-base scope replacement (status={derive_status}); "
                  f"existing metrics preserved")

        # ---- derive-analytics snapshot replacement ----
        analytics_status, analytics_payload = load_analytics_run(base, ticker)
        if analytics_status == "loaded":
            analytics_rows = (analytics_payload.get("analytics_metrics")
                              or analytics_payload.get("ratio_metrics") or [])
            a_managed = (analytics_payload.get("metadata", {}) or {}).get("managed_rule_ids")
            a_scope = analytics_delete_scope(a_managed)
            client = client or supabase_client()

            # facts-wins fetch+filter BEFORE the scope delete (half-update safety).
            kept, dropped = analytics_rows, 0
            if analytics_rows:
                facts_keys = fetch_facts_logical_keys(client, ticker)
                kept = filter_derived_rows_against_facts(analytics_rows, facts_keys)
                dropped = len(analytics_rows) - len(kept)

            a_del = (client.table("sec_financial_metrics")
                     .delete()
                     .eq("ticker", ticker)
                     .in_("provenance->>rule_id", a_scope)
                     .execute())
            print(f"  cleared derive-analytics scope ({len(a_scope)} rule_ids): "
                  f"sec_financial_metrics ({len(a_del.data)} rows deleted)")
            if analytics_rows:
                if dropped:
                    print(f"  facts-wins: dropped {dropped} derived row(s) "
                          f"colliding with disclosed facts")
                if kept:
                    client.table("sec_financial_metrics").upsert(
                        kept, on_conflict="cell_id").execute()
                print(f"  upserted: sec_financial_metrics ({len(kept)} analytics rows)")
        elif analytics_status == "missing_run":
            print(f"  (no derive-analytics output found for {ticker} — ratios not refreshed)")
        elif analytics_status == "incomplete_run":
            print(f"  ⚠ derive-analytics latest run INCOMPLETE for {ticker}; existing rows preserved")
        print(f"  ✓ Upsert complete.")
    else:
        print(f"\n  ✓ Dry-run complete. Gate passed. Re-run with --apply to write to Supabase.")


if __name__ == "__main__":
    main()
