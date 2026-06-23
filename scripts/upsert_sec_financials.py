"""Upsert SEC v2 financials (AAOI / INTC / SNDK / ...) → Supabase.

Spec: tmp/financials-viewer-redesign-plan.md §20 (v5.1) execution plan steps 4-7.

Pipeline:
  1. Load 3 source JSONs (parse-10QK-gaap, parse-8k-nongaap, parse-SEC-supplement)
     + edges (calc / presentation / def_dim).
  2. Run sec_json_adapter to normalize → DB-ready rows.
  3. Preflight: period_end map + ISO date validate + rejected log.
  4. Dry-run mode (--dry-run): print stats, NEVER touch DB. Default.
  5. Real-run mode (--apply): upsert to 4 tables (companies / facts /
     dimensional_facts / edges). Metrics table left empty (derive skills
     Phase 2 will populate).

Usage:
    # dry-run AAOI
    python scripts/upsert_sec_financials.py AAOI

    # real upsert
    python scripts/upsert_sec_financials.py AAOI --apply

Skill output is expected at:
    Obsidian/Khouse/Semiconductors/{TICKER}/01_Source/SEC Filings/Skill_Output/
        parse-10QK-gaap/{TICKER}_gaap_facts.json
        parse-10QK-gaap/{TICKER}_gaap_edges_cal.json
        parse-10QK-gaap/{TICKER}_gaap_edges_pre.json
        parse-10QK-gaap/{TICKER}_sign_flip_concepts.json
        parse-8k-nongaap/{TICKER}_nongaap.json
        parse-SEC-supplement/{TICKER}_supplement_facts_v3.json
        parse-SEC-supplement/{TICKER}_supplement_edges_v3.json
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

from _shared import sec_json_adapter as A  # noqa: E402
from _shared.presentation_resolver import (  # noqa: E402
    accepted_face_concepts,
    select_network,
)

OBSIDIAN_BASE = Path(os.environ.get(
    "OBSIDIAN_VAULT",
    os.path.expanduser("~/Obsidian"),
))

BATCH_SIZE = 500

# Authoritative list of all rule_ids derive-base has EVER produced. Used:
#   (a) missing_run gate — when local output absent, identify derive-base-managed
#       rows for the conflict check
#   (b) snapshot replacement — delete scope is union(this run's managed_rule_ids,
#       this list) so that when a previously-used rule stops firing for a period
#       (e.g. Q4_FY_MINUS_Q1Q2Q3 replaced by Q4_FY_MINUS_9M after 9M becomes
#       derivable via IBT identity), the orphan rows still get cleared.
# Update when adding a new derive-base rule.
DERIVE_BASE_RULE_IDS_FALLBACK = (
    # Q2 / Q3 single-quarter reconstruction from disclosed YTD (P2.1).
    "Q2_6M_MINUS_Q1",
    "Q3_9M_MINUS_6M",
    # Q4 reconstruction
    "Q4_FY_MINUS_9M",
    "Q4_FY_MINUS_Q1Q2Q3",
    # GAAP / Non-GAAP identity allowlists
    "STATIC_ALLOWLIST",
    "NG_ALLOWLIST",
    # XBRL calculation linkbase derivation
    "CALC_LINKBASE",
    # Identity rules — derive-base outputs concrete rule_ids, not prefixes,
    # so we list each here. When a new IDENTITY_* rule lands in derive-base, add it.
    "IDENTITY_IBT_FROM_OP_PLUS_NONOP",
    "IDENTITY_IBT_FROM_OP_MINUS_INTEXP_PLUS_NONOP",
)

# Owned rule registry for derive-analytics. Mirrors derive-base's fallback:
# the analytics snapshot-replacement delete scope must cover every rule the
# skill can emit, even when the current run / payload metadata lists a subset,
# so a rule that produced 0 rows this run still has its stale Supabase rows
# cleared. Keep in sync with rules_ratios.ALL_RULE_IDS. When a new analytics
# rule lands, add its rule_id here.
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
    # Phase B absolute-value (numerator-only) derivations.
    "FCF_CFO_MINUS_CAPEX",
    # EBITDA (SEC C&DI 103.01 bottom-up) — absolute value + margin.
    "EBITDA_NI_INT_TAX_DA",
    "RATIO_EBITDA_MARGIN_PCT",
    # Adjusted EBITDA Margin (cross-version: adjusted_ebitda@NON_GAAP / revenue@GAAP).
    "RATIO_ADJUSTED_EBITDA_MARGIN_PCT",
    # BVPS = total_equity / common_shares_outstanding (USD_per_share, BS instant).
    "RATIO_BVPS",
    # Phase D EL2 cross-period (TTM) ratios.
    "RATIO_ROE",
    "RATIO_ROA",
    # EL2 expansion Phase 1 — efficiency (asset turnover + DSO/DIO/DPO/CCC).
    "RATIO_ASSET_TURNOVER",
    "RATIO_DIO",
    "RATIO_DSO",
    "RATIO_DPO",
    "RATIO_CCC",
    # EL2 expansion Phase 2 — YoY growth.
    "RATIO_REVENUE_YOY",
    "RATIO_NET_INCOME_YOY",
    "RATIO_EPS_DILUTED_YOY",
    # EL2 expansion Phase 3 — ROIC.
    "RATIO_ROIC",
    # EL2 leverage — Net Debt / EBITDA.
    "RATIO_NET_DEBT_TO_EBITDA",
)


def analytics_delete_scope(payload_managed_rule_ids) -> list[str]:
    """Delete scope for derive-analytics snapshot replacement.

    Union of the payload's self-declared managed_rule_ids with the owned
    registry fallback, so legacy/partial payloads can never under-delete and
    leave stale analytics rows behind.
    """
    return sorted(
        set(payload_managed_rule_ids or ()) | set(DERIVE_ANALYTICS_RULE_IDS_FALLBACK)
    )


def derive_base_delete_scope(payload_managed_rule_ids) -> list[str]:
    """Delete scope for derive-base snapshot replacement (symmetric with
    analytics_delete_scope).

    Union of the run's self-declared managed_rule_ids with the owned fallback,
    so a rule that stopped firing this run (e.g. a ticker that no longer emits
    Q2/Q3 reconstructions because its single quarters became directly disclosed)
    still has its orphan Supabase rows cleared rather than stranded.
    """
    return sorted(
        set(payload_managed_rule_ids or ()) | set(DERIVE_BASE_RULE_IDS_FALLBACK)
    )


def latest_run_json_path(vault: Path, ticker: str, skill_dir: str, json_filename: str):
    """Path to the CURRENT latest run's JSON for a skill, or None if absent.
    Mirrors _load_skill_run's latest-folder selection so callers can compare a
    recorded input path against what the upsert would actually consume now."""
    base = (vault / "Khouse" / "Semiconductors" / ticker
            / "01_Source" / "SEC Filings" / "Skill_Output" / skill_dir)
    if not base.exists():
        return None
    runs = sorted(p for p in base.iterdir() if p.is_dir())
    if not runs:
        return None
    p = runs[-1] / json_filename
    return p if p.exists() else None


def analytics_derive_base_is_current(analytics_payload: dict, latest_db_json_path) -> bool:
    """True if the analytics run consumed the CURRENT latest derive-base run.

    Guards the path-version drift case the freshness hash misses: a newer
    derive-base run exists but the old folder is still on disk, so analytics'
    recorded old derive_base path still hashes correctly. If derive-base is
    loaded, analytics' derive_base input path must resolve to the current latest
    derive-base JSON; otherwise it's stale (fresh derive-base + old ratios).
    """
    if latest_db_json_path is None:
        return True  # no current derive-base → nothing to be stale against
    info = ((analytics_payload or {}).get("metadata", {}) or {}).get("input_files", {}) or {}
    db = info.get("derive_base")
    if not isinstance(db, dict) or not db.get("path"):
        return False  # derive-base exists but analytics recorded no derive_base lineage
    return Path(db["path"]).resolve() == Path(latest_db_json_path).resolve()


def analytics_required_keys(derive_status: str) -> set:
    """Minimum input_files lineage the analytics freshness gate must require.

    derive-analytics consumes parse facts + derive-base (Q4/identity). When
    derive-base is currently loaded, the analytics run MUST have consulted it —
    so require `derive_base` lineage. Otherwise an analytics run produced before
    derive-base existed (input_files lacks derive_base) would pass the gate and
    ship raw-only ratios next to fresh derive-base Q4 metrics (mixed-vintage).
    In a parse-only / no-derive-base refresh we don't require derive_base.
    """
    keys = {"gaap_facts"}
    if derive_status == "loaded":
        keys.add("derive_base")
    return keys


def _ratio_logical_key(r) -> tuple:
    return (r.get("period"), r.get("period_kind"), r.get("version"),
            r.get("statement"), r.get("uni_account"))


def filter_derived_rows_against_facts(derived_rows, facts_logical_keys) -> list:
    """facts-wins at the STORAGE boundary (P2.1): drop any derived metrics row
    whose logical identity collides with a disclosed `sec_financial_facts` row,
    so the collision is removed before the metrics upsert — not merely hidden by
    the read-model API. facts/metrics use different cell_id schemes, so the
    comparison is on the logical tuple (period|period_kind|version|statement|
    uni_account), per docs/financials-data-rules.md §SEC v2.

    Statement-agnostic: the same guard covers RATIO ratios today and Phase B/C
    absolute-value derivations (FCF→CF, EBITDA→IS) once they ship — provided the
    caller passes the broadened all-statement fact-key set (fetch_facts_logical_keys).
    """
    keys = set(facts_logical_keys)
    return [r for r in derived_rows if _ratio_logical_key(r) not in keys]


# Back-compat alias (Phase 0 name `filter_ratio_rows_against_facts`). The RATIO
# scoping always lived in the *caller's* fact-key set, not this function, so the
# alias safely points at the broadened generic.
filter_ratio_rows_against_facts = filter_derived_rows_against_facts


def fetch_facts_logical_keys(client, ticker: str, page: int = 1000) -> set:
    """Fetch ALL disclosed-facts logical keys for a ticker, across every
    statement (IS/BS/CF/RATIO), paginating past Supabase's default 1000-row cap.

    Feeds the storage-boundary facts-wins guard. The Phase 0 version selected
    only `statement='RATIO'` with a single un-paginated execute() — safe while
    derive-analytics emitted RATIO ratios only. Phase B/C add CF (FCF) and IS
    (EBITDA) absolute-value derivations that can collide with disclosed facts in
    those statements, and IS+BS+CF facts per ticker can exceed 1000 rows, so the
    fetch must drop the statement filter AND page.
    """
    keys: set = set()
    frm = 0
    while True:
        # .order("cell_id") gives a stable unique total order so .range() page
        # boundaries are a deterministic contract — without it PostgREST/Postgres
        # make NO ordering guarantee and adjacent pages could overlap or skip
        # rows, silently dropping disclosed facts from the guard's key set.
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


# ---- IO helpers --------------------------------------------------------------


def skill_output_dir(ticker: str) -> Path:
    return OBSIDIAN_BASE / "Khouse" / "Semiconductors" / ticker / "01_Source" / "SEC Filings" / "Skill_Output"


def load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def load_sources(ticker: str) -> dict:
    """Load all source JSONs (some may be absent).

    Adds (Task 8) the PDF-faithful display inputs: `gaap_labels` (labels.json)
    and per-statement audited NLM ordering artifacts. Both are optional —
    absence just means fewer display ordinals resolve (the next task's coverage
    gate decides whether that's acceptable).
    """
    base = skill_output_dir(ticker)
    nlm_dir = base / "nlm-statement-order"

    def _latest_dimensional_analytics(base, ticker):
        d = base / "derive-dimensional-analytics"
        if not d.exists():
            return None
        runs = sorted([r for r in d.iterdir() if r.is_dir() and r.name[:4].isdigit()],
                      reverse=True)
        for run in runs:
            cand = run / f"{ticker}_dimensional_analytics.json"
            if cand.exists():
                return load_json(cand)
        return None

    return {
        "gaap_facts": load_json(base / "parse-10QK-gaap" / f"{ticker}_gaap_facts.json"),
        "gaap_edges_cal": load_json(base / "parse-10QK-gaap" / f"{ticker}_gaap_edges_cal.json"),
        "gaap_edges_pre": load_json(base / "parse-10QK-gaap" / f"{ticker}_gaap_edges_pre.json"),
        "gaap_labels": load_json(base / "parse-10QK-gaap" / f"{ticker}_gaap_labels.json"),
        "sign_flip": load_json(base / "parse-10QK-gaap" / f"{ticker}_sign_flip_concepts.json"),
        "nongaap": load_json(base / "parse-8k-nongaap" / f"{ticker}_nongaap.json"),
        "supplement_facts": load_json(base / "parse-SEC-supplement" / f"{ticker}_supplement_facts_v3.json"),
        "supplement_edges": load_json(base / "parse-SEC-supplement" / f"{ticker}_supplement_edges_v3.json"),
        "period_anchor": load_json(base / "parse-SEC-supplement" / f"{ticker}_period_anchor_validation.json"),
        "dimensional_analytics": _latest_dimensional_analytics(base, ticker),
        "nlm_order": {
            stmt: load_json(nlm_dir / f"{ticker}_{stmt}_nlm_order.json")
            for stmt in ("IS", "BS", "CF")
        },
    }


# ---- Pipeline ----------------------------------------------------------------


def _extract_labels_map(gaap_labels) -> dict:
    """Tolerant extraction of labels.json → ``{concept_qname: [{role,lang,text}]}``.

    parse-10QK-gaap's build_separated emits a top-level mapping; defensively
    unwrap a ``{"labels": {...}}`` envelope if present.
    """
    if not gaap_labels:
        return {}
    if isinstance(gaap_labels, dict) and "labels" in gaap_labels and isinstance(gaap_labels["labels"], dict):
        return gaap_labels["labels"]
    return gaap_labels if isinstance(gaap_labels, dict) else {}


def _read_audited_order(artifact: dict) -> dict:
    """Read ``{cell_id: ordinal}`` from an AUDITED artifact via
    nlm_statement_order.read_audited_order.

    Imported lazily by file path (the module lives alongside this one in
    ``scripts/``) so the upsert module never mutates global ``sys.path`` at
    import time — that pollutes module resolution for the rest of a pytest run.
    """
    import importlib.util
    mod_path = Path(__file__).resolve().parent / "nlm_statement_order.py"
    spec = importlib.util.spec_from_file_location("_nlm_statement_order", str(mod_path))
    nlm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(nlm)
    return nlm.read_audited_order(artifact)


def _build_audited_orders(nlm_order: dict | None) -> dict:
    """Build the per-statement audited-order map the adapter consumes.

    For each statement whose NLM artifact is present AND status=="audited",
    produce::

        {statement: {"cell_id_to_ordinal": {cell_id: ordinal},
                     "source_doc": str, "period": str, "artifact_hash": str}}

    A ``pending_audit`` (or absent) artifact contributes nothing — G1/G7:
    unaudited order MUST never feed production. ``read_audited_order`` already
    enforces the status gate (returns {} otherwise), so an unaudited artifact
    yields an empty cell_id map and is skipped.
    """
    import hashlib
    out: dict = {}
    for stmt, artifact in (nlm_order or {}).items():
        if not artifact:
            continue
        cell_map = _read_audited_order(artifact)
        if not cell_map:
            continue  # not audited, or no matched lines
        artifact_hash = hashlib.sha256(
            json.dumps(artifact, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        out[stmt] = {
            "cell_id_to_ordinal": cell_map,
            "source_doc": artifact.get("source_doc"),
            "period": artifact.get("period"),
            "artifact_hash": artifact_hash,
        }
    return out


def attach_display_to_batch(batch: A.NormalizedBatch, sources: dict) -> None:
    """Resolve PDF-faithful display_label + ordinal + provenance on GAAP facts.

    Per statement (IS/BS/CF): select the presentation network from edges_pre,
    then call the adapter's ``attach_display_metadata`` over that statement's
    facts. Non-GAAP facts are not statement-display rows here (they have their
    own version/path); only GAAP facts get display metadata. Spec Task 8.
    """
    edges = (sources.get("gaap_edges_pre") or {}).get("edges", []) \
        if isinstance(sources.get("gaap_edges_pre"), dict) else []
    labels = _extract_labels_map(sources.get("gaap_labels"))
    audited_orders = _build_audited_orders(sources.get("nlm_order"))

    gaap_facts = [f for f in batch.facts if f.version == "GAAP"]
    for statement in ("IS", "BS", "CF"):
        stmt_facts = [f for f in gaap_facts if f.statement == statement]
        if not stmt_facts:
            continue
        facts_concepts = {
            (f.source_account or "").rsplit(":", 1)[-1]
            for f in stmt_facts if f.source_account
        }
        network_role = select_network(edges, statement, facts_concepts or None)
        # T14 Issue2: accepted face concepts = UNION across ALL matching face
        # networks (10-K full ∪ 10-Q condensed), basis for narrow note-level
        # exclusion of tag_like facts not present on any face statement.
        accepted = accepted_face_concepts(edges, statement)
        A.attach_display_metadata(
            stmt_facts,
            statement=statement,
            edges=edges,
            labels=labels,
            network_role=network_role,
            accepted_concepts=accepted,
            audited_orders=audited_orders,
        )
        # Whole-row redundancy suppression (dedup spec v2): null a prose/tag row
        # that duplicates another row's economic line. Runs AFTER attach (needs
        # display_negated for the value-agreement veto) and per statement.
        A.dedup_redundant_rows(
            stmt_facts, statement=statement, edges=edges, labels=labels,
        )

    _print_note_level_exclusions(batch.ticker, gaap_facts)


def _print_note_level_exclusions(ticker: str, gaap_facts: list) -> None:
    """Audit print: every GAAP fact auto-excluded as note-level (T14 Issue2).

    Lists ticker / statement / uni_account / source_account / xbrl_tag / period
    for each fact now display_eligible=False with provenance reason
    `note_level_not_in_face_network`, grouped + counted per statement. No silent
    truncation — a human must be able to audit every concept classified
    note-level. Printed dry-run & real-run alike."""
    excluded = [
        f for f in gaap_facts
        if f.display_eligible is False
        and (f.provenance or {}).get("display_exclusion_reason")
            == "note_level_not_in_face_network"
    ]
    print("\n  === Note-level exclusions (T14 Issue2: tag_like not in face network) ===")
    if not excluded:
        print("    (none)")
        return
    by_stmt: dict[str, list] = {}
    for f in excluded:
        by_stmt.setdefault(f.statement, []).append(f)
    for statement in ("IS", "BS", "CF"):
        rows = by_stmt.get(statement)
        if not rows:
            continue
        print(f"    {statement}: {len(rows)} excluded")
        for f in rows:
            print(
                f"        - {ticker} / {statement} / {f.uni_account} / "
                f"{f.source_account} / {f.xbrl_tag} / {f.period}"
            )


def normalize(ticker: str, sources: dict) -> A.NormalizedBatch:
    """Run full adapter pipeline; return NormalizedBatch with rows + validation."""
    batch = A.NormalizedBatch(ticker=ticker)

    if sources["gaap_facts"] is None:
        raise SystemExit(f"GAAP facts missing for {ticker} — run parse-10QK-gaap first")

    gaap_meta = sources["gaap_facts"]["metadata"]
    sign_flip = (sources["sign_flip"] or {}).get("concepts", [])
    batch.company = A.adapt_company(gaap_meta, sign_flip_concepts=sign_flip)

    pe_map = A.build_period_end_map(
        gaap_meta, (sources["gaap_facts"] or {}).get("facts"))

    # GAAP facts
    gaap_rows, gaap_rej = A.adapt_gaap_facts(sources["gaap_facts"], pe_map)
    batch.facts.extend(gaap_rows)
    batch.rejected.extend(gaap_rej)

    # Non-GAAP facts (optional)
    if sources["nongaap"]:
        ng_rows, ng_rej = A.adapt_nongaap_facts(sources["nongaap"], pe_map)
        batch.facts.extend(ng_rows)
        batch.rejected.extend(ng_rej)

    # Dimensional facts (optional)
    if sources["supplement_facts"]:
        sp_rows, sp_rej, sp_dedupe, sp_conflicts = A.adapt_supplement_facts(sources["supplement_facts"])
        batch.dimensional.extend(sp_rows)
        batch.rejected.extend(sp_rej)
        batch.dedupe_stats = sp_dedupe
        batch.value_conflicts = sp_conflicts

    # Derived dimensional analytics (segment operating margin). Rides the SAME
    # dimensional batch but carries provenance.derived=true + rule_id; its cell_ids
    # differ from raw-segment rows (uni_account=operating_margin_pct), so it never
    # collides with or clears the raw segment values.
    if sources.get("dimensional_analytics"):
        da_rows, da_rej = A.adapt_dimensional_analytics_facts(sources["dimensional_analytics"])
        batch.dimensional.extend(da_rows)
        batch.rejected.extend(da_rej)

    # Edges
    for key, edge_type in [
        ("gaap_edges_cal", "calc"),
        ("gaap_edges_pre", "presentation"),
        ("supplement_edges", "def_dim"),
    ]:
        if sources[key]:
            batch.edges.extend(A.adapt_edges(sources[key], ticker, edge_type))

    # Task 8: resolve PDF-faithful display_label + ordinal + provenance on GAAP
    # facts (parse skills untouched — all resolution lives here at the upsert
    # boundary). Reads labels.json + edges_pre + audited NLM ordering artifacts.
    attach_display_to_batch(batch, sources)

    return batch


# ---- Coverage hard gate (spec G4) -------------------------------------------
#
# 100% of display-eligible FACT rows (per ticker × statement IS/BS/CF) must carry
# an ordinal, else we MUST NOT ship a half-ordered Statement view — fail loud and
# block --apply (a human adds an NLM artifact line / audits before retry).
#
# Denominator = display-eligible FACT rows only. EXCLUDED:
#   - YTD-duration rows (period_kind == "ytd_duration") — never a Statement row.
#   - metric-only rows: derived single quarters (derived_q2/q3/q4) + absolute-value
#     metrics (ebitda / free_cash_flow). These live in sec_financial_metrics and
#     attach by uni_account on the frontend; the adapter never assigns them a
#     statement ordinal (spec §16). They are not in batch.facts today, but the
#     denominator excludes them explicitly so coverage_report is correct even if a
#     caller passes a mixed row set.
#   - display-INELIGIBLE synthetic SUM-of-multiple-PDF-lines rows
#     (display_eligible is False) — they build no Statement-view row.

_COVERAGE_STATEMENTS = ("IS", "BS", "CF")
_YTD_PERIOD_KIND = "ytd_duration"
# Mirrors sec_json_adapter._DERIVED_SINGLE_QUARTER_PKINDS (kept local so the gate
# has no import-time dependency on a private adapter name).
_DERIVED_SINGLE_QUARTER_PKINDS = frozenset({"derived_q2", "derived_q3", "derived_q4"})
# Absolute-value metric-only uni_accounts (derive-analytics) that are never
# Statement facts. Excluded from the coverage denominator by uni_account.
_METRIC_ONLY_UNI = frozenset({"ebitda", "adjusted_ebitda", "free_cash_flow"})


def _row_attr(row, name, default=None):
    """Read `name` from a FactRow dataclass OR a plain dict (coverage_report is
    spec'd to accept generic adapted rows)."""
    if isinstance(row, dict):
        return row.get(name, default)
    return getattr(row, name, default)


def _is_coverage_eligible(row) -> bool:
    """True iff `row` belongs in the coverage denominator (display-eligible FACT)."""
    if _row_attr(row, "statement") not in _COVERAGE_STATEMENTS:
        return False
    # Non-GAAP (8-K reconciliation) facts are an OVERLAY keyed by uni_account onto
    # the GAAP face rows — they are NOT independent face-statement rows and have no
    # XBRL presentation network, so attach_display_to_batch only resolves GAAP
    # facts (it skips version!=GAAP). Counting Non-GAAP facts in the GAAP-statement
    # coverage denominator would falsely fail the gate (they can never carry an
    # XBRL ordinal). Exclude them.
    if _row_attr(row, "version") != "GAAP":
        return False
    if _row_attr(row, "period_kind") == _YTD_PERIOD_KIND:
        return False
    if _row_attr(row, "period_kind") in _DERIVED_SINGLE_QUARTER_PKINDS:
        return False
    if _row_attr(row, "uni_account") in _METRIC_ONLY_UNI:
        return False
    if _row_attr(row, "display_eligible") is False:
        return False
    return True


def coverage_report(rows) -> dict:
    """Per-statement coverage of display-eligible FACT rows.

    Returns ``{statement: {"eligible": int, "with_ordinal": int,
    "missing": [{statement, uni_account, source_account, period}, ...]}}`` for
    each statement (IS/BS/CF) that has at least one eligible row.
    """
    report: dict = {}
    for row in rows:
        if not _is_coverage_eligible(row):
            continue
        stmt = _row_attr(row, "statement")
        bucket = report.setdefault(stmt, {"eligible": 0, "with_ordinal": 0, "missing": []})
        bucket["eligible"] += 1
        if _row_attr(row, "ordinal") is not None:
            bucket["with_ordinal"] += 1
        else:
            bucket["missing"].append({
                "statement": stmt,
                "uni_account": _row_attr(row, "uni_account"),
                "source_account": _row_attr(row, "source_account"),
                "period": _row_attr(row, "period"),
            })
    return report


def coverage_pct(bucket: dict) -> float:
    """Coverage % for one statement bucket (100.0 when no eligible rows)."""
    eligible = bucket.get("eligible", 0)
    if eligible == 0:
        return 100.0
    return round(100.0 * bucket.get("with_ordinal", 0) / eligible, 1)


def coverage_gate_blocks_apply(report: dict) -> bool:
    """Apply-blocking predicate: True iff ANY statement is < 100% covered."""
    return any(bucket.get("with_ordinal", 0) < bucket.get("eligible", 0)
               for bucket in report.values())


def print_coverage_report(report: dict) -> bool:
    """Print the per-statement coverage section. Return True if gate passes
    (all statements 100%)."""
    blocks = coverage_gate_blocks_apply(report)
    print(f"\n  === Coverage Gate (spec G4: display-eligible rows need ordinal) ===")
    if not report:
        print(f"    (no display-eligible fact rows)")
        return True
    for stmt in _COVERAGE_STATEMENTS:
        bucket = report.get(stmt)
        if bucket is None:
            continue
        pct = coverage_pct(bucket)
        ok = bucket["with_ordinal"] >= bucket["eligible"]
        mark = "✓" if ok else "✗"
        line = (f"    [{mark}] {stmt} {pct}% "
                f"({bucket['with_ordinal']}/{bucket['eligible']})")
        if not ok:
            line += f" — {len(bucket['missing'])} row(s) missing ordinal"
        print(line)
        if not ok:
            for m in bucket["missing"]:
                label = m.get("uni_account") or m.get("source_account") or "?"
                print(f"        - {stmt} {label} ({m.get('period')})")
    return not blocks


def print_report(batch: A.NormalizedBatch) -> bool:
    """Print dry-run / real-run report. Return True if gate passes."""
    print(f"\n=== {batch.ticker} normalization report ===")
    print(f"  company: {batch.company.company_name} ({batch.company.exchange}) cik={batch.company.cik}")
    print(f"  filings indexed: {len(batch.company.filings)}")
    print(f"  sign_flip_concepts: {len(batch.company.sign_flip_concepts)}")

    fact_by_stmt = Counter(r.statement for r in batch.facts)
    fact_by_ver = Counter(r.version for r in batch.facts)
    print(f"\n  facts: {len(batch.facts)} rows")
    print(f"    by statement: {dict(fact_by_stmt)}")
    print(f"    by version: {dict(fact_by_ver)}")
    print(f"    by period_kind: {dict(Counter(r.period_kind for r in batch.facts))}")
    print(f"    by unit: {dict(Counter(r.unit for r in batch.facts))}")

    print(f"\n  dimensional: {len(batch.dimensional)} rows")
    if batch.dimensional:
        print(f"    by axis: {dict(Counter(r.axis for r in batch.dimensional))}")
        print(f"    by period_kind: {dict(Counter(r.period_kind for r in batch.dimensional))}")
        print(f"    by unit: {dict(Counter(r.unit for r in batch.dimensional))}")
        print(f"    dedupe_stats: {batch.dedupe_stats}")

    print(f"\n  edges: {len(batch.edges)} rows")
    if batch.edges:
        print(f"    by type: {dict(Counter(r.edge_type for r in batch.edges))}")

    # Identity uniqueness
    fact_ids = [r.cell_id for r in batch.facts]
    dim_ids = [r.cell_id for r in batch.dimensional]
    edge_ids = [r.edge_id for r in batch.edges]
    fact_dup = len(fact_ids) - len(set(fact_ids))
    dim_dup = len(dim_ids) - len(set(dim_ids))
    edge_dup = len(edge_ids) - len(set(edge_ids))

    print(f"\n  identity uniqueness:")
    print(f"    facts: {len(set(fact_ids))}/{len(fact_ids)} unique (dup={fact_dup})")
    print(f"    dimensional: {len(set(dim_ids))}/{len(dim_ids)} unique (dup={dim_dup})")
    print(f"    edges: {len(set(edge_ids))}/{len(edge_ids)} unique (dup={edge_dup})")

    # Gate
    gate_pass = True
    print(f"\n  === §20.6 Open Gate ===")
    checks = [
        ("rejected rows = 0", len(batch.rejected) == 0, f"rejected={len(batch.rejected)}"),
        ("value conflicts = 0", len(batch.value_conflicts) == 0, f"conflicts={len(batch.value_conflicts)}"),
        ("facts identity unique", fact_dup == 0, f"dup={fact_dup}"),
        ("dimensional identity unique", dim_dup == 0, f"dup={dim_dup}"),
        ("edges identity unique", edge_dup == 0, f"dup={edge_dup}"),
    ]
    for name, ok, detail in checks:
        mark = "✓" if ok else "✗"
        print(f"    [{mark}] {name} ({detail})")
        if not ok:
            gate_pass = False

    if batch.rejected:
        print(f"\n  rejected rows (first 5):")
        for r in batch.rejected[:5]:
            print(f"    {r['source']} idx={r['idx']} reason={r['reason']}")

    if batch.value_conflicts:
        print(f"\n  value conflicts (first 5):")
        for c in batch.value_conflicts[:5]:
            print(f"    key={c['dedupe_key']}")
            for v in c['values']:
                print(f"      value={v['value']} dec={v.get('decimals')} src={v.get('source_doc')}")

    # Coverage hard gate (spec G4): 100% of display-eligible fact rows per
    # statement must carry an ordinal, else block --apply. Reported here (dry-run
    # & real-run alike); folds into the overall gate result.
    report = coverage_report(batch.facts)
    coverage_pass = print_coverage_report(report)
    if not coverage_pass:
        gate_pass = False

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
    """asdict + JSON-friendly fixups (drop None unit/value where col is NOT NULL etc.).

    `display_eligible` is an adapter-internal flag (a display-ineligible synthetic
    SUM core builds no Statement-view row prototype) — there is NO such DB column,
    so it is stripped here. `display_label` IS a column (migration
    2026060500_add_display_label.sql) and is kept. `display_negated` IS also a
    column (migration 2026060700_add_display_negated.sql) — the PDF-faithful sign
    flag — and flows through asdict unchanged (nullable boolean).

    `ordinal` is a smallint column, but XBRL presentation `order` (and thus the
    resolved ordinal) arrives as a float (e.g. 3.0). Coerce integer-valued floats
    to int so PostgREST accepts them. Fail loud on a genuinely fractional order
    (e.g. 1.5): truncating it to 1 would silently collide with another line's
    position — a real filer using fractional orders needs a schema decision
    (smallint → numeric), not a silent truncation.
    """
    d = asdict(row)
    d.pop("display_eligible", None)
    # Only FactRow carries `ordinal`. DimensionalRow has no such field/column —
    # never ADD the key (sec_financial_dimensional_facts would reject it).
    if "ordinal" in d:
        d["ordinal"] = _coerce_ordinal(d["ordinal"])
    return d


def _coerce_ordinal(ordinal):
    """smallint-safe ordinal: None passes through; an integer-valued float/int is
    cast to int; a fractional value raises ValueError (no silent truncation)."""
    if ordinal is None:
        return None
    f = float(ordinal)
    if f != int(f):
        raise ValueError(
            f"non-integer ordinal {ordinal!r} cannot be stored in smallint column "
            f"without truncation/collision. The `ordinal` column needs a schema "
            f"decision (smallint → numeric) before fractional XBRL orders ship."
        )
    return int(f)


def apply(batch: A.NormalizedBatch) -> None:
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

    # 3. dimensional_facts — snapshot-replace per ticker. Dimensional cell_id
    # encodes the period, so a re-labeled period (e.g. an upstream 52/53-week
    # fiscal-period fix) writes new cell_ids and would leave the old-labeled rows
    # orphaned (this table has no per-row managed delete scope). The supplement
    # batch IS the full current dimensional snapshot for the ticker, so clear the
    # ticker's rows then re-insert. GUARD: only clear when there is a batch to
    # replace them with — a run without supplement data must never wipe the ticker.
    if batch.dimensional:
        tkr = batch.company.ticker
        before = (client.table("sec_financial_dimensional_facts")
                  .select("cell_id", count="exact").eq("ticker", tkr).execute()).count
        client.table("sec_financial_dimensional_facts").delete().eq("ticker", tkr).execute()
        print(f"  cleared dimensional scope: sec_financial_dimensional_facts "
              f"(ticker={tkr}, {before} rows deleted)")
    n = upsert_batch(client, "sec_financial_dimensional_facts", [row_to_dict(r) for r in batch.dimensional])
    print(f"  upserted: sec_financial_dimensional_facts ({n} rows)")

    # 4. edges
    n = upsert_batch(client, "sec_financial_edges", [row_to_dict(r) for r in batch.edges])
    print(f"  upserted: sec_financial_edges ({n} rows)")


# ---- Derived metrics (derive-base output) ------------------------------------


def load_derived_metrics(vault: Path, ticker: str) -> tuple[str, list[dict]]:
    """Back-compat wrapper around `load_derived_run` that returns only the
    (status, rows) pair. Existing call sites + tests use this signature."""
    status, payload = load_derived_run(vault, ticker)
    return status, (payload.get("derived_metrics", []) if payload else [])


def load_derived_run(vault: Path, ticker: str) -> tuple[str, dict | None]:
    """Read latest derive-base run for `ticker` and return the full payload.

    Returns tri-state (status, payload):
      - ("missing_run", None)     — no derive-base output dir / no runs yet
      - ("incomplete_run", None)  — run folder exists but JSON missing / unparseable
      - ("loaded", payload_dict)  — JSON loaded; derived_metrics may be [] (legit empty)

    Callers needing freshness check (R6-F1) should use this and read
    `payload["metadata"]["input_files"]` to verify source hashes.
    """
    return _load_skill_run(vault, ticker, "derive-base", f"{ticker}_derived.json", "derived_metrics")


def load_analytics_run(vault: Path, ticker: str) -> tuple[str, dict | None]:
    """Read latest derive-analytics run for `ticker`. Same tri-state contract
    as load_derived_run. Rows live under the canonical "analytics_metrics" key
    (ratios AND absolute-value metrics like FCF). The legacy "ratio_metrics" key
    is still accepted as a defensive fallback for any pre-existing artifact (the
    writer no longer emits it)."""
    return _load_skill_run(vault, ticker, "derive-analytics", f"{ticker}_analytics.json",
                           ("analytics_metrics", "ratio_metrics"))


def _load_skill_run(vault: Path, ticker: str, skill_dir: str,
                    json_filename: str, rows_key) -> tuple[str, dict | None]:
    """`rows_key` may be a single key or a tuple of candidate keys (the run is
    'loaded' if ANY candidate is present) — lets derive-analytics accept both the
    canonical `analytics_metrics` and the legacy `ratio_metrics` key."""
    base = (vault / "Khouse" / "Semiconductors" / ticker
            / "01_Source" / "SEC Filings" / "Skill_Output" / skill_dir)
    if not base.exists():
        return ("missing_run", None)
    runs = sorted(p for p in base.iterdir() if p.is_dir())
    if not runs:
        return ("missing_run", None)
    payload_path = runs[-1] / json_filename
    if not payload_path.exists():
        return ("incomplete_run", None)
    try:
        payload = json.loads(payload_path.read_text())
    except (OSError, json.JSONDecodeError):
        return ("incomplete_run", None)
    keys = (rows_key,) if isinstance(rows_key, str) else tuple(rows_key)
    if all(payload.get(k) is None for k in keys):
        return ("incomplete_run", None)
    return ("loaded", payload)


# R7-F1: minimum input_files contract a derive-base run must carry to be
# considered a verifiable snapshot. Missing/empty input_files or absence of
# any required key fails the freshness gate, otherwise an old/manual JSON
# that lacks lineage would bypass R6-F1.
_REQUIRED_INPUT_FILE_KEYS = frozenset({"gaap_inline", "gaap_facts", "gaap_edges_cal"})


def verify_derived_freshness(payload: dict, required_keys=None) -> list[dict]:
    """Re-hash every source file referenced in derived payload.metadata
    .input_files and compare to the stored sha256. Returns a list of mismatch
    descriptors (empty = fresh). R6-F1 / R7-F1.

    `required_keys` is the minimum input_files contract for the producing skill
    (defaults to derive-base's `_REQUIRED_INPUT_FILE_KEYS`; derive-analytics
    passes its own, e.g. {"gaap_facts"}). A missing required key fails closed so
    a lineage-poor JSON can't bypass the gate.

    Each mismatch: {"key", "path", "stored_sha256", "current_sha256", "reason"}
    reason ∈ {"hash_mismatch", "file_missing", "input_files_missing",
              "input_file_key_missing"}.
    """
    import hashlib
    if required_keys is None:
        required_keys = _REQUIRED_INPUT_FILE_KEYS
    metadata = (payload or {}).get("metadata") or {}
    input_files = metadata.get("input_files")
    mismatches: list[dict] = []

    # R7-F1: minimum metadata contract.
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
        if info is None:  # legitimate optional source (e.g. nongaap absent)
            continue
        # R8-F1: info must be a dict with non-empty path AND sha256. Anything
        # else is malformed metadata — refuse to treat as fresh.
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
        h = hashlib.sha256()
        h.update(data)
        current = h.hexdigest()
        if current != stored:
            mismatches.append({
                "key": key, "path": str(path),
                "stored_sha256": stored, "current_sha256": current,
                "reason": "hash_mismatch",
            })
    return mismatches


# ---- CLI ---------------------------------------------------------------------


def main():
    p = argparse.ArgumentParser()
    p.add_argument("ticker", help="ticker symbol (case-insensitive)")
    p.add_argument("--apply", action="store_true", help="real upsert to Supabase (default: dry-run)")
    p.add_argument("--allow-missing-derived", action="store_true",
                   help="Allow --apply when local derive-base output is missing "
                        "AND Supabase already has derive-base-managed metrics "
                        "for this ticker. Default is fail-closed (R7-F2) to "
                        "prevent mixed-vintage state (new facts + stale metrics).")
    p.add_argument("--allow-period-anomaly", action="store_true",
                   help="Override the period-anchor gate: upsert dimensional rows even "
                        "when {ticker}_period_anchor_validation.json reports Tier-1 "
                        "fiscal-period mislabels. Default fail-closed — dimensional rows "
                        "are withheld (existing DB rows preserved) until labels resolve.")
    args = p.parse_args()
    ticker = args.ticker.upper()

    sources = load_sources(ticker)
    batch = normalize(ticker, sources)

    # Period-anchor gate (MVP, parse-SEC-supplement Stage-B). A fiscal-period
    # mislabel poisons every dimensional row's period label, so withhold the whole
    # dimensional batch (the snapshot-replace is guarded by `if batch.dimensional`,
    # so existing rows are preserved — never wiped). GAAP / Non-GAAP unaffected.
    # FAIL-CLOSED: when there ARE dimensional rows to protect, the gate fires not
    # only on a Tier-1 anomaly but also when the validation artifact is MISSING
    # (can't confirm labels) or anchored 0 quarters (window excluded every 10-K
    # FYE anchor) — otherwise the guardrail is trivially bypassed by a deleted /
    # never-generated artifact or a truncated parse window.
    pa_artifact = sources.get("period_anchor")
    pa_val = (pa_artifact or {}).get("validation", {}) or {}
    pa_tier1 = pa_val.get("tier1", [])
    pa_summary = pa_val.get("summary", {}) or {}
    has_dim = bool(batch.dimensional)
    gate_reason = None
    if pa_tier1:
        gate_reason = f"{len(pa_tier1)} Tier-1 period anomaly(ies)"
    elif has_dim and pa_artifact is None:
        gate_reason = "period-anchor validation artifact MISSING (re-run parse_instance_xbrl)"
    elif has_dim and pa_summary.get("anchored_quarters", 0) == 0:
        gate_reason = ("period-anchor validated 0 quarters — window likely excludes the "
                       "10-K FYE anchor; cannot confirm period labels")
    if gate_reason and not args.allow_period_anomaly:
        print(f"\n  ⚠ PERIOD-ANCHOR GATE: {gate_reason} for {ticker} "
              f"— withholding {len(batch.dimensional)} dimensional rows (existing preserved).")
        for a in pa_tier1:
            print(f"      ❌ {a.get('accession')} [{a.get('reportDate')}] kind={a.get('kind')} "
                  f"resolved={a.get('resolved_label')} expected={a.get('expected_label')}")
        print("      Resolve labels / re-parse, or pass --allow-period-anomaly to override.")
        batch.dimensional = []
    elif gate_reason:
        print(f"\n  ⚠ PERIOD-ANCHOR: {gate_reason} OVERRIDDEN via --allow-period-anomaly")

    gate_pass = print_report(batch)

    if not gate_pass:
        print("\n  ✗ Gate FAILED — refusing to upsert. Fix issues above and re-run.")
        sys.exit(1)

    derive_status, derived_payload = load_derived_run(OBSIDIAN_BASE, ticker)
    derived_rows = (derived_payload or {}).get("derived_metrics", []) if derived_payload else []
    if derive_status == "loaded":
        print(f"\n  + derive-base output: {len(derived_rows)} rows (status=loaded)")
    elif derive_status == "missing_run":
        print(f"\n  (no derive-base output found for {ticker})")
    elif derive_status == "incomplete_run":
        print(f"\n  ⚠ derive-base latest run INCOMPLETE for {ticker}")

    # R4-F2: incomplete_run must abort the whole apply, not just skip the
    # derive scope. Otherwise facts/dimensional/edges get refreshed while
    # metrics stay stale → Viewer shows mixed-vintage data.
    if args.apply and derive_status == "incomplete_run":
        print(f"\n  ✗ Refusing --apply: derive-base latest run is incomplete for {ticker}.")
        print(f"     Re-run derive-base for {ticker} and retry. Existing DB rows preserved.")
        sys.exit(2)

    # R7-F2: missing_run is only safe when DB has no derive-base-managed
    # metrics for this ticker (first-time ingest). When DB already has them,
    # parse-only refresh would create mixed-vintage state (new facts + stale
    # metrics). Fail-closed unless --allow-missing-derived is explicit.
    #
    # Scope is identified by provenance.rule_id (filter on JSON path), using
    # the DERIVE_BASE_RULE_IDS_FALLBACK constant. derive-analytics writes
    # different rule_ids and is not touched.
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
            print(f"     Run derive-base for {ticker} first, or pass "
                  f"--allow-missing-derived to accept parse-only refresh "
                  f"(existing metrics will not be touched).")
            sys.exit(4)

    # R6-F1: source-hash freshness gate. If `derive_status == "loaded"` but
    # the underlying parse files have changed since the derive run produced
    # this output, refuse --apply — otherwise we'd write new facts and
    # stale derived metrics into Supabase, creating mixed-vintage Viewer
    # state. Workflow fix: re-run derive-base, then retry upsert.
    if args.apply and derive_status == "loaded" and derived_payload is not None:
        mismatches = verify_derived_freshness(derived_payload)
        if mismatches:
            print(f"\n  ✗ Refusing --apply: derive-base output is STALE for {ticker}.")
            print(f"     {len(mismatches)} input source(s) changed since derive run:")
            for m in mismatches:
                reason = m["reason"]
                if reason == "file_missing":
                    print(f"       - {m['key']}: file missing at {m['path']}")
                elif reason == "file_unreadable":
                    print(f"       - {m['key']}: file unreadable at {m['path']} (OSError)")
                elif reason == "input_files_missing":
                    print(f"       - metadata.input_files absent — derive payload lacks source-snapshot contract")
                elif reason == "input_file_key_missing":
                    print(f"       - {m['key']}: required input_files key absent in derive payload")
                elif reason == "input_file_metadata_invalid":
                    print(f"       - {m['key']}: malformed metadata (missing path or sha256)")
                else:
                    print(f"       - {m['key']}: stored={m['stored_sha256'][:12]}…  current={m['current_sha256'][:12]}…")
            print(f"     Re-run derive-base for {ticker} and retry. Existing DB rows preserved.")
            sys.exit(3)

    # Phase 0 P0.3 + P1.1: derive-analytics apply-path gate. Mirrors derive-base:
    # every unsafe analytics state must fail closed BEFORE apply(batch), so fresh
    # facts are never written alongside stale/missing analytics rows (mixed-vintage).
    #   - incomplete_run → corrupt run, never safe → exit 2.
    #   - missing_run + DB already has analytics-managed rows → exit 4, unless
    #     --allow-missing-derived (parse-only refresh; existing ratios preserved).
    #   - loaded + stale inputs → exit 3.
    if args.apply:
        _afresh_status, _afresh_payload = load_analytics_run(OBSIDIAN_BASE, ticker)
        if _afresh_status == "incomplete_run":
            print(f"\n  ✗ Refusing --apply: derive-analytics latest run INCOMPLETE for {ticker} "
                  f"(folder present, no {ticker}_analytics.json).")
            print(f"     Re-run derive-analytics for {ticker} and retry. Existing DB rows preserved.")
            sys.exit(2)
        if _afresh_status == "missing_run" and not args.allow_missing_derived:
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
                print(f"     Run derive-analytics for {ticker} first, or pass "
                      f"--allow-missing-derived to accept parse-only refresh "
                      f"(existing ratios will not be touched).")
                sys.exit(4)
        if _afresh_status == "loaded" and _afresh_payload is not None:
            a_mismatches = verify_derived_freshness(
                _afresh_payload, required_keys=analytics_required_keys(derive_status)
            )
            if a_mismatches:
                print(f"\n  ✗ Refusing --apply: derive-analytics output is STALE for {ticker}.")
                print(f"     {len(a_mismatches)} input source(s) changed since the analytics run:")
                for m in a_mismatches:
                    reason = m["reason"]
                    if reason in ("file_missing", "file_unreadable"):
                        print(f"       - {m['key']}: {reason} at {m['path']}")
                    elif reason in ("input_files_missing", "input_file_key_missing",
                                    "input_file_metadata_invalid"):
                        print(f"       - {m['key']}: {reason}")
                    else:
                        print(f"       - {m['key']}: stored={str(m['stored_sha256'])[:12]}…  "
                              f"current={str(m['current_sha256'])[:12]}…")
                print(f"     Re-run derive-analytics for {ticker} and retry. Existing DB rows preserved.")
                sys.exit(3)
            # P1 (3rd-pass): path-version drift. The hash check above re-hashes
            # the recorded derive_base path, which still matches if an OLDER
            # derive-base run is on disk. When derive-base is loaded, the
            # analytics run must point to the CURRENT latest derive-base run,
            # else it shipped ratios from an older derive-base than the one this
            # upsert writes (fresh derive-base + stale ratios).
            if derive_status == "loaded":
                latest_db = latest_run_json_path(
                    OBSIDIAN_BASE, ticker, "derive-base", f"{ticker}_derived.json"
                )
                if not analytics_derive_base_is_current(_afresh_payload, latest_db):
                    print(f"\n  ✗ Refusing --apply: derive-analytics ran against an older "
                          f"derive-base run than the current latest for {ticker}.")
                    print(f"     Re-run derive-analytics for {ticker} (so it consumes the "
                          f"latest derive-base) and retry. Existing DB rows preserved.")
                    sys.exit(3)

    if args.apply:
        print(f"\n=== Real upsert to Supabase ===")
        # Lazily obtained so the parse-only / no-derived path never opens a DB
        # connection (and analytics DB ops never UnboundLocalError when the
        # derive-base branch that used to create `client` is skipped — P1.2).
        client = None
        apply(batch)
        # Fail-closed snapshot replacement (Codex round-2 F5 + round-3 F2/F3
        # + round-4 F2): only DELETE the derive-base scope when status=loaded.
        # incomplete_run was already rejected above; missing_run keeps any
        # existing metrics untouched (parse-only refresh path).
        #
        # Scope is determined by derive-base's self-declared managed_rule_ids
        # in payload metadata. derive-analytics uses different rule_ids and
        # is not touched. Falls back to DERIVE_BASE_RULE_IDS_FALLBACK if the
        # payload predates managed_rule_ids metadata (legacy output).
        if derive_status == "loaded":
            managed = (derived_payload.get("metadata", {}) or {}).get("managed_rule_ids") or []
            # Union with fallback list so rule_ids that stopped firing in this
            # run (but were used in a previous run) still get their orphan rows
            # cleared. Without this, a rule swap (e.g. Q4_FY_MINUS_Q1Q2Q3 →
            # Q4_FY_MINUS_9M after 9M becomes derivable via IBT identity) would
            # leave the old DB row stranded, creating silent duplicates.
            delete_scope = derive_base_delete_scope(managed)
            client = supabase_client()
            del_r = (client.table("sec_financial_metrics")
                     .delete()
                     .eq("ticker", ticker)
                     .in_("provenance->>rule_id", delete_scope)
                     .execute())
            print(f"  cleared derive-base scope ({len(delete_scope)} rule_ids, "
                  f"current managed={managed}): "
                  f"sec_financial_metrics ({len(del_r.data)} rows deleted)")
            if derived_rows:
                client.table("sec_financial_metrics").upsert(
                    derived_rows, on_conflict="cell_id"
                ).execute()
                print(f"  upserted: sec_financial_metrics ({len(derived_rows)} rows)")
            else:
                print(f"  (derive-base loaded an intentionally empty set — DB derive scope is now empty)")
        else:
            # missing_run reaches here only with --allow-missing-derived (R7-F2);
            # no Supabase round-trip needed for the derive scope.
            print(f"  ⚠ skipping derive-base scope replacement (status={derive_status}); existing metrics preserved")

        # ---- derive-analytics snapshot replacement ----
        # Independent scope from derive-base. Uses its own managed_rule_ids.
        # If analytics output is missing/incomplete we just skip — analytics
        # is purely additive. No fail-closed gate yet; it's MVP. Phase B: rows
        # may now include absolute-value metrics (FCF), not just ratios.
        analytics_status, analytics_payload = load_analytics_run(OBSIDIAN_BASE, ticker)
        if analytics_status == "loaded":
            analytics_rows = (analytics_payload.get("analytics_metrics")
                              or analytics_payload.get("ratio_metrics") or [])
            a_managed = (analytics_payload.get("metadata", {}) or {}).get("managed_rule_ids")
            a_scope = analytics_delete_scope(a_managed)
            client = client or supabase_client()  # P1.2: may be unset if derive-base was skipped

            # facts-wins at storage boundary (P2.1): never write a derived row
            # whose logical identity collides with a disclosed facts row.
            # Broadened past RATIO (Phase B prerequisite) to ALL statements +
            # paginated, so future FCF (CF) / EBITDA (IS) absolute-value
            # derivations are covered, and tickers with >1000 IS/BS/CF facts
            # aren't silently truncated.
            #
            # P2.2: do this read-only fetch + filter BEFORE the scope delete.
            # The fetch is now a heavier multi-page read; if it fails mid-way we
            # must not have already deleted the analytics rows (which would leave
            # a half-update: old rows gone, new rows never written). facts_keys
            # doesn't depend on the delete, so compute kept first, mutate after.
            kept, dropped = analytics_rows, 0
            if analytics_rows:
                facts_keys = fetch_facts_logical_keys(client, ticker)
                kept = filter_derived_rows_against_facts(analytics_rows, facts_keys)
                dropped = len(analytics_rows) - len(kept)

            # Always clear the full owned scope (union payload + fallback) so a
            # rule that emitted 0 rows this run can't leave stale Supabase rows.
            a_del = (client.table("sec_financial_metrics")
                     .delete()
                     .eq("ticker", ticker)
                     .in_("provenance->>rule_id", a_scope)
                     .execute())
            print(f"  cleared derive-analytics scope (rule_ids={a_scope}): "
                  f"sec_financial_metrics ({len(a_del.data)} rows deleted)")
            if analytics_rows:
                if dropped:
                    print(f"  facts-wins: dropped {dropped} derived row(s) "
                          f"colliding with disclosed facts")
                if kept:
                    client.table("sec_financial_metrics").upsert(
                        kept, on_conflict="cell_id"
                    ).execute()
                print(f"  upserted: sec_financial_metrics ({len(kept)} analytics rows)")
        elif analytics_status == "missing_run":
            print(f"  (no derive-analytics output found for {ticker} — ratios not refreshed)")
        elif analytics_status == "incomplete_run":
            print(f"  ⚠ derive-analytics latest run INCOMPLETE for {ticker}; existing analytics rows preserved")
        print(f"  ✓ Upsert complete.")
    else:
        print(f"\n  ✓ Dry-run complete. Gate passed. Re-run with --apply to write to Supabase.")


if __name__ == "__main__":
    main()
