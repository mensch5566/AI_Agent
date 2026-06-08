"use client";

import { useEffect, useState } from "react";
import type { ApiResponse, Cell, MatrixCell, PeriodKind, Statement, Version } from "./types";
import {
  DERIVED_NONGAAP_ABSOLUTE_ROWS,
  IS_ROWS,
  CF_ROWS,
  LONG_TAIL_ROLLUP_HINTS,
  ROWS_BY_STATEMENT,
  comparePeriods,
} from "./constants";

/**
 * useFinancialMatrix(ticker)
 *
 * Fetches /api/financials/[ticker] and builds a pivot matrix per (statement × version).
 *
 * Matrix shape:
 *   rows: uni_account in metric dictionary order
 *   cols: periods sorted oldest → newest
 *   cell: {cell?, status} — status='PENDING' if no DB row found
 *
 * Statement-aware period filtering (per docs/financials-data-rules.md §SEC v2):
 *   IS/CF + quarterly:       quarter_duration ∪ derived_q2 ∪ derived_q3 ∪ derived_q4
 *   IS/CF + annual:          fy_annual_duration
 *   BS + quarterly:          instant_period_end (period = Qx_FYyyyy)
 *   BS + annual:             instant_period_end (period = FYyyyy)
 *   RATIO + quarterly:       quarter_duration ∪ derived_q2/q3/q4 ∪ instant_period_end (Qx_FYyyyy) ∪ ttm_duration (Qx_FYyyyy, EL2 roe/roa)
 *   RATIO + annual:          fy_annual_duration ∪ instant_period_end (FYyyyy)
 *
 * RATIO mixes duration-based ratios (margins, ETR computed off IS) and
 * instant-based ratios (current_ratio computed off BS). Both period_kinds are
 * allowed; instant cells are constrained by period-name pattern to avoid leakage.
 */

export type Frequency = "quarterly" | "annual";

export type Matrix = {
  periods: string[];                       // column headers, sorted
  rows: { key: string; label: string; kind: string; indent: number }[];
  cells: Record<string, Record<string, MatrixCell>>;  // [uni_account][period] -> MatrixCell
};

export type UseFinancialMatrixState = {
  loading: boolean;
  error: string | null;
  data: ApiResponse | null;
};

export function useFinancialData(ticker: string): UseFinancialMatrixState {
  const [state, setState] = useState<UseFinancialMatrixState>({
    loading: true,
    error: null,
    data: null,
  });

  useEffect(() => {
    let cancelled = false;
    setState({ loading: true, error: null, data: null });
    fetch(`/api/financials/${encodeURIComponent(ticker)}`, { cache: "no-store" })
      .then(async (r) => {
        if (!r.ok) {
          const body = await r.json().catch(() => ({}));
          throw new Error(body.error || `HTTP ${r.status}`);
        }
        return r.json() as Promise<ApiResponse>;
      })
      .then((d) => {
        if (!cancelled) setState({ loading: false, error: null, data: d });
      })
      .catch((e) => {
        if (!cancelled) setState({ loading: false, error: String(e?.message ?? e), data: null });
      });
    return () => {
      cancelled = true;
    };
  }, [ticker]);

  return state;
}

// Single-quarter IS/CF cells: directly disclosed (quarter_duration) plus
// derive-base reconstructions from YTD cumulatives (derived_q2 = 6M−Q1,
// derived_q3 = 9M−6M, derived_q4 = FY−9M). YTD-CF tickers (e.g. INTC) only
// disclose 6M/9M, so their Q2/Q3 single-quarter flows come from derived_q2/q3.
const QUARTERLY_PKINDS_IS_CF: PeriodKind[] = [
  "quarter_duration",
  "derived_q2",
  "derived_q3",
  "derived_q4",
];
const ANNUAL_PKINDS_IS_CF: PeriodKind[] = ["fy_annual_duration"];
const BS_PKINDS: PeriodKind[] = ["instant_period_end"];

// EL2 TTM-derived ratios are quarterly-only. The `ttm_duration` period_kind must
// only be honored for these uni_accounts so a stray `ttm_duration` row for any
// other RATIO key can never leak into the grid silently (keeps UI aligned with the
// EL2 spec — Codex P3, 2026-06-02). Phase 1 efficiency (asset_turnover/dio/dso/dpo/
// ccc) are TTM ratios too; YoY (quarter_duration) is deliberately NOT here.
const TTM_RATIO_ROWS = new Set<string>([
  "roe",
  "roa",
  "roic",
  "asset_turnover",
  "dio",
  "dso",
  "dpo",
  "ccc",
  "net_debt_to_ebitda",
]);

// Absolute-value metric-only uni_accounts (derive-analytics) that are NOT
// disclosed statement lines — they live in the Ratios/Derived subsection, never
// inline in IS/BS/CF (spec §P2.3). Mirrors scripts/upsert_sec_financials.py
// `_METRIC_ONLY_UNI`. A metric cell for one of these must never create a row.
const METRIC_ONLY_UNI = new Set<string>(["ebitda", "adjusted_ebitda", "free_cash_flow"]);

// Derived single-quarter reconstructions (derive-base): they carry no
// source_account/ordinal and ATTACH to a display-eligible prototype row by
// uni_account — they never create a prototype themselves (spec §P1.2/G5).
const DERIVED_SINGLE_QUARTER_PKINDS = new Set<PeriodKind>([
  "derived_q2",
  "derived_q3",
  "derived_q4",
]);

// A long-tail bucket uni_account holds many source_accounts under one key, so a
// bucket member's rowId must include source_account to stay distinct.
function isLongTailUni(uni: string): boolean {
  return uni.endsWith("_long_tail");
}

// rowId contract: core rows key on uni_account so a derived single-quarter
// metric (bucket-less, keyed only by uni_account) can attach to its PDF row;
// long-tail bucket members key on uni_account|source_account to disambiguate the
// many source_accounts that share one bucket uni_account (spec §P1.2/P2.6).
function rowIdOf(uni: string, sourceAccount: string | null): string {
  return isLongTailUni(uni) && sourceAccount != null ? `${uni}|${sourceAccount}` : uni;
}

// A direct fact is a display-eligible row prototype iff it carries resolved
// display metadata (display_label and/or ordinal). A display-INELIGIBLE
// synthetic SUM core (e.g. selling_general_administrative = SUM(S&M+G&A)) has
// BOTH display_label and ordinal null — it builds no row prototype, and a
// derived single-quarter cell must not pull it back via the shared uni_account
// (spec §G7, plan note). Metric cells are never prototypes (handled separately).
function isDisplayEligiblePrototype(c: Cell): boolean {
  if (c.source_table !== "facts") return false;
  if (METRIC_ONLY_UNI.has(c.uni_account)) return false;
  // Long-tail member needs a source_account to form a distinct rowId/label.
  if (isLongTailUni(c.uni_account) && c.source_account == null) return false;
  return c.display_label != null || c.ordinal != null;
}

function isFyPeriod(p: string): boolean {
  return /^FY\d{4}$/.test(p);
}
function isQuarterPeriod(p: string): boolean {
  return /^Q\d_FY\d{4}$/.test(p);
}
function isYearEndQuarterPeriod(p: string): boolean {
  return /^Q4_FY\d{4}$/.test(p);
}
function q4ToFy(p: string): string {
  const m = /^Q4_FY(\d{4})$/.exec(p);
  return m ? `FY${m[1]}` : p;
}

export function buildMatrix(
  cells: Cell[],
  statement: Statement,
  version: Version,
  frequency: Frequency,
  viewMode: "pdf" | "uni" = "pdf",
): Matrix {
  // Year-end balance-sheet snapshots are stored as `Q4_FYyyyy` / instant_period_end
  // (a balance sheet is point-in-time; the fiscal-year-end snapshot IS the
  // Q4-end snapshot — there is no separate `FYyyyy` instant row). In annual
  // mode, remap those Q4 instant periods to `FYyyyy` so the year-end snapshot
  // (BS rows + BS-derived ratios like current_ratio) aligns under the annual
  // column next to the `fy_annual_duration` IS/CF data. Quarterly mode keeps
  // `Q4_FYyyyy` as-is so the snapshot lands in the Q4 column.
  const sourceCells =
    frequency === "annual"
      ? cells.map((c) =>
          c.period_kind === "instant_period_end" && isYearEndQuarterPeriod(c.period)
            ? { ...c, period: q4ToFy(c.period) }
            : c,
        )
      : cells;

  // Filter cells by statement + version + period_kind/period
  const filtered = sourceCells.filter((c) => {
    if (c.statement !== statement) return false;
    if (c.version !== version) return false;
    if (statement === "BS") {
      if (!BS_PKINDS.includes(c.period_kind)) return false;
      return frequency === "quarterly" ? isQuarterPeriod(c.period) : isFyPeriod(c.period);
    }
    if (statement === "RATIO") {
      // Allow both duration-based ratios (margins, ETR) and instant-based
      // ratios (current_ratio off BS). Instant cells must additionally match
      // the freq's period-name shape so we don't accidentally pull stray
      // periods into the RATIO grid.
      if (c.period_kind === "instant_period_end") {
        return frequency === "quarterly" ? isQuarterPeriod(c.period) : isFyPeriod(c.period);
      }
      // EL2 TTM-derived ratios (roe/roa/roic + efficiency dio/dso/dpo/ccc/
      // asset_turnover — see TTM_RATIO_ROWS) are quarterly-only; period is the TTM
      // end quarter (Qx_FYyyyy). The annual EL2 variant is fy_annual_duration
      // (handled by ANNUAL_PKINDS_IS_CF below), so ttm_duration never shows in
      // annual mode. Restrict to the explicit TTM_RATIO_ROWS allowlist so an
      // unexpected ttm_duration row for another RATIO key can't silently render.
      if (c.period_kind === "ttm_duration") {
        return (
          frequency === "quarterly" &&
          isQuarterPeriod(c.period) &&
          TTM_RATIO_ROWS.has(c.uni_account)
        );
      }
      const allowed = frequency === "quarterly" ? QUARTERLY_PKINDS_IS_CF : ANNUAL_PKINDS_IS_CF;
      return allowed.includes(c.period_kind);
    }
    // IS / CF
    const allowed = frequency === "quarterly" ? QUARTERLY_PKINDS_IS_CF : ANNUAL_PKINDS_IS_CF;
    return allowed.includes(c.period_kind);
  });

  // Collect periods
  const periodSet = new Set<string>(filtered.map((c) => c.period));
  const periods = Array.from(periodSet).sort(comparePeriods);

  // -------------------------------------------------------------------------
  // RATIO statement: unchanged — fixed RATIO_ROWS dictionary, summed long-tail
  // (RATIO has no long-tail buckets today, but keep the dictionary path intact;
  // this task only restructures IS/BS/CF row building — spec §8 "RATIO as-is").
  // -------------------------------------------------------------------------
  if (statement === "RATIO") {
    return buildDictionaryMatrix(filtered, statement, periods);
  }

  // uni_account mode: route the three statements through the fixed-dictionary
  // builder (canonical core rows + long-tail SUM buckets). PDF mode falls through
  // to the data-driven path below. (spec: view-mode toggle.)
  if (viewMode === "uni") {
    return buildDictionaryMatrix(filtered, statement, periods);
  }

  // -------------------------------------------------------------------------
  // IS / BS / CF: data-driven PDF-faithful rows. Each row prototype comes from
  // a DIRECT, display-eligible fact (carries source_account + display metadata);
  // rows are ordered by `ordinal` (nulls last, stable) with label = display_label
  // (fallback source_account). Derived single-quarter metrics (derived_q2/q3/q4)
  // attach by uni_account to the matching prototype row — they never create a
  // ghost row, and they never resurrect a display-ineligible synthetic core.
  // (spec §P1.2/P2.6/G5/G2.)
  // -------------------------------------------------------------------------

  // Pass 1: build row prototypes from display-eligible direct facts.
  // Map rowId -> prototype state. `seq` records first-seen order so the sort is
  // stable for equal/null ordinals. `protoPeriod`/`protoOrdinal`/`protoLabel`
  // are chosen deterministically (latest period wins) so a row's label/ordinal
  // don't depend on cell iteration order (spec §G5).
  type Proto = {
    rowId: string;
    uni: string;
    seq: number;
    ordinal: number | null;
    label: string;
    protoPeriod: string; // period that currently owns label/ordinal
    isLongTail: boolean;
  };
  const protos = new Map<string, Proto>();
  let seqCounter = 0;
  for (const c of filtered) {
    if (!isDisplayEligiblePrototype(c)) continue;
    const rowId = rowIdOf(c.uni_account, c.source_account);
    const label = c.display_label ?? c.source_account ?? c.uni_account;
    const existing = protos.get(rowId);
    if (!existing) {
      protos.set(rowId, {
        rowId,
        uni: c.uni_account,
        seq: seqCounter++,
        ordinal: c.ordinal,
        label,
        protoPeriod: c.period,
        isLongTail: isLongTailUni(c.uni_account),
      });
      continue;
    }
    // Deterministic prototype: the latest period's fact owns label + ordinal.
    if (comparePeriods(c.period, existing.protoPeriod) > 0) {
      existing.protoPeriod = c.period;
      existing.ordinal = c.ordinal;
      existing.label = label;
    }
  }

  // Order rows by ordinal asc (nulls last), tie-broken by first-seen seq (stable).
  const orderedProtos = Array.from(protos.values()).sort((a, b) => {
    const ao = a.ordinal;
    const bo = b.ordinal;
    if (ao == null && bo == null) return a.seq - b.seq;
    if (ao == null) return 1; // nulls last
    if (bo == null) return -1;
    if (ao !== bo) return ao - bo;
    return a.seq - b.seq;
  });

  // For derived single-quarter attach we resolve a uni_account back to the
  // display-eligible prototype rowId. A display-INELIGIBLE synthetic core never
  // entered `protos`, so its uni_account has no entry here and a derived cell for
  // it is correctly dropped (not pulled back into the statement). Core rowId ===
  // uni_account; long-tail buckets are not the attach target for bucket-less
  // derived metrics (those are keyed by uni_account only), so map only core unis.
  const uniToCoreRowId = new Map<string, string>();
  for (const p of orderedProtos) {
    if (!p.isLongTail) uniToCoreRowId.set(p.uni, p.rowId);
  }

  // Initialize the pivot grid.
  const cellMap: Record<string, Record<string, MatrixCell>> = {};
  for (const p of orderedProtos) {
    cellMap[p.rowId] = {};
    for (const per of periods) cellMap[p.rowId][per] = { status: "PENDING" };
  }

  // Pass 2: fill cells.
  for (const c of filtered) {
    // Metric-only absolute-value rows (ebitda / fcf) never render inline.
    if (METRIC_ONLY_UNI.has(c.uni_account)) continue;

    if (DERIVED_SINGLE_QUARTER_PKINDS.has(c.period_kind)) {
      // Attach by uni_account to its display-eligible core prototype. If no such
      // prototype exists (display-ineligible synthetic core), drop it — never
      // create a ghost row, never pull the synthetic back.
      const rowId = uniToCoreRowId.get(c.uni_account);
      if (rowId == null) continue;
      if (cellMap[rowId]?.[c.period] === undefined) continue;
      cellMap[rowId][c.period] = { cell: c, status: c.status };
      continue;
    }

    // Direct facts (and any other allowed cell): write to their own prototype
    // row. Only display-eligible facts have a row; everything else is dropped.
    const rowId = rowIdOf(c.uni_account, c.source_account);
    if (cellMap[rowId]?.[c.period] === undefined) continue;
    cellMap[rowId][c.period] = { cell: c, status: c.status };
  }

  return {
    periods,
    rows: orderedProtos.map((p) => ({
      key: p.rowId,
      label: p.label,
      kind: p.isLongTail ? "long_tail_bucket" : "core",
      indent: 0,
    })),
    cells: cellMap,
  };
}

// Legacy fixed-dictionary matrix builder, retained for RATIO (and as a label
// fallback path). Rows come from ROWS_BY_STATEMENT; long-tail buckets sum their
// children with rollup suppression. IS/BS/CF no longer use this — they are
// data-driven off the ticker's actual disclosed facts (Task 11).
export function buildDictionaryMatrix(
  filtered: Cell[],
  statement: Statement,
  periods: string[],
): Matrix {
  // ebitda / free_cash_flow are DERIVED (never on a filing's face three statements);
  // they render only in the Ratios-tab DerivedNonGaap subsection, so they must never
  // appear inline here. Matches the PDF path's METRIC_ONLY_UNI suppression. No-op for
  // RATIO (its RATIO_ROWS contains no raw ebitda/free_cash_flow key).
  const rows = ROWS_BY_STATEMENT[statement].filter((r) => !METRIC_ONLY_UNI.has(r.key));

  const longTailKeys = new Set(rows.filter((r) => r.kind === "long_tail_bucket").map((r) => r.key));

  const cellMap: Record<string, Record<string, MatrixCell>> = {};
  for (const row of rows) {
    cellMap[row.key] = {};
    for (const p of periods) {
      cellMap[row.key][p] = { status: "PENDING" };
    }
  }
  const longTailBuf: Record<string, Record<string, Cell[]>> = {};
  for (const c of filtered) {
    if (!cellMap[c.uni_account]) continue;
    if (!cellMap[c.uni_account][c.period]) continue;
    if (longTailKeys.has(c.uni_account)) {
      (longTailBuf[c.uni_account] ??= {})[c.period] ??= [];
      longTailBuf[c.uni_account][c.period].push(c);
    } else {
      cellMap[c.uni_account][c.period] = { cell: c, status: c.status };
    }
  }
  for (const k of longTailKeys) {
    const byPeriod = longTailBuf[k];
    if (!byPeriod) continue;
    for (const p of Object.keys(byPeriod)) {
      const rawChildren = byPeriod[p];
      const suppressed: Cell[] = [];
      const children = rawChildren.filter((c) => {
        const hintTarget =
          ((c.long_tail_metadata as Record<string, unknown> | null)?.rolls_up_to as
            | string
            | undefined) ?? LONG_TAIL_ROLLUP_HINTS[c.xbrl_tag ?? ""];
        if (!hintTarget) return true;
        const coreCell = cellMap[hintTarget]?.[p];
        const corePopulated = !!(coreCell && coreCell.cell && coreCell.status !== "PENDING");
        if (corePopulated) {
          suppressed.push(c);
          return false;
        }
        return true;
      });
      if (children.length === 0) continue;
      const summed = children.reduce((s, c) => s + c.value * (c.weight ?? 1), 0);
      const base = children[0];
      const synthetic: Cell = {
        ...base,
        uni_account: k,
        source_account: children.length === 1 ? base.source_account : "SUM(long_tail)",
        xbrl_tag: null,
        // bucket sign = the summed value's own sign; never inherit a child's
        // display_negated (the `...base` spread copies children[0]'s flag, which
        // would make displayValue negate the WHOLE bucket — latent sign bug).
        display_negated: null,
        value: summed,
        weight: 1,
        provenance: {
          aggregation: "long_tail_sum",
          children_count: children.length,
          suppressed_count: suppressed.length,
          children: children.map((c) => ({
            source_account: c.source_account,
            xbrl_tag: c.xbrl_tag,
            value: c.value,
            weight: c.weight,
            rolls_up_to:
              ((c.long_tail_metadata as Record<string, unknown> | null)?.rolls_up_to as
                | string
                | undefined) ?? null,
          })),
          suppressed: suppressed.map((c) => ({
            source_account: c.source_account,
            xbrl_tag: c.xbrl_tag,
            value: c.value,
            rolls_up_to:
              ((c.long_tail_metadata as Record<string, unknown> | null)?.rolls_up_to as
                | string
                | undefined) ?? LONG_TAIL_ROLLUP_HINTS[c.xbrl_tag ?? ""] ?? null,
          })),
        },
      };
      cellMap[k][p] = { cell: synthetic, status: "SOURCE_OF_TRUTH" };
    }
  }

  return {
    periods,
    rows: rows.map((r) => ({ key: r.key, label: r.label, kind: r.kind, indent: r.indent ?? 0 })),
    cells: cellMap,
  };
}

// ---------------------------------------------------------------------------
// Derived / Non-GAAP ABSOLUTE-VALUE subsection (Task 13, spec §P2.3).
//
// `ebitda` (statement=IS) and `free_cash_flow` (statement=CF) are derived $
// measures that are METRIC_ONLY_UNI — buildMatrix deliberately drops them from
// the inline IS/CF statements, and they are NOT in RATIO_ROWS, so neither
// matrix surfaces them. This selector scans the raw cells array and gathers ONLY
// those metric cells into a Matrix-shaped result so the Viewer can render a
// dedicated "Derived / Non-GAAP" subsection (formatted as $, not ratios).
//
// Rows always render in the canonical DERIVED_NONGAAP_ABSOLUTE_ROWS order (even
// when a ticker has no data for one of them), for visual continuity. Period and
// version filtering mirror the IS/CF duration rules: quarter_duration ∪
// derived_q2/q3/q4 in quarterly mode, fy_annual_duration in annual mode.
// ---------------------------------------------------------------------------

// Canonical $-row labels, sourced from the statement dictionaries so the
// subsection reads identically to the (now-removed) inline EBITDA / FCF lines.
const DERIVED_NONGAAP_LABELS: Record<string, string> = {
  ebitda: IS_ROWS.find((r) => r.key === "ebitda")?.label ?? "EBITDA",
  free_cash_flow: CF_ROWS.find((r) => r.key === "free_cash_flow")?.label ?? "Free Cash Flow",
};

export function buildDerivedNonGaapRows(
  cells: Cell[],
  version: Version,
  frequency: Frequency,
): Matrix {
  const wanted = new Set<string>(DERIVED_NONGAAP_ABSOLUTE_ROWS);
  const allowedPkinds =
    frequency === "quarterly" ? QUARTERLY_PKINDS_IS_CF : ANNUAL_PKINDS_IS_CF;

  const filtered = cells.filter((c) => {
    if (!wanted.has(c.uni_account)) return false;
    if (c.source_table !== "metrics") return false;
    if (c.version !== version) return false;
    return allowedPkinds.includes(c.period_kind);
  });

  const periods = Array.from(new Set(filtered.map((c) => c.period))).sort(comparePeriods);

  // Fixed row order from the canonical list; always present for continuity.
  const rowKeys = DERIVED_NONGAAP_ABSOLUTE_ROWS;
  const cellMap: Record<string, Record<string, MatrixCell>> = {};
  for (const key of rowKeys) {
    cellMap[key] = {};
    for (const p of periods) cellMap[key][p] = { status: "PENDING" };
  }
  for (const c of filtered) {
    if (cellMap[c.uni_account]?.[c.period] === undefined) continue;
    cellMap[c.uni_account][c.period] = { cell: c, status: c.status };
  }

  return {
    periods,
    rows: rowKeys.map((key) => ({
      key,
      label: DERIVED_NONGAAP_LABELS[key] ?? key,
      kind: "derived_nongaap_absolute",
      indent: 0,
    })),
    cells: cellMap,
  };
}
