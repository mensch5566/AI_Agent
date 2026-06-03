"use client";

import { useEffect, useState } from "react";
import type { ApiResponse, Cell, MatrixCell, PeriodKind, Statement, Version } from "./types";
import { LONG_TAIL_ROLLUP_HINTS, ROWS_BY_STATEMENT, comparePeriods } from "./constants";

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
 *   IS/CF + quarterly:       quarter_duration ∪ derived_q4
 *   IS/CF + annual:          fy_annual_duration
 *   BS + quarterly:          instant_period_end (period = Qx_FYyyyy)
 *   BS + annual:             instant_period_end (period = FYyyyy)
 *   RATIO + quarterly:       quarter_duration ∪ derived_q4 ∪ instant_period_end (Qx_FYyyyy) ∪ ttm_duration (Qx_FYyyyy, EL2 roe/roa)
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

const QUARTERLY_PKINDS_IS_CF: PeriodKind[] = ["quarter_duration", "derived_q4"];
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
): Matrix {
  const rows = ROWS_BY_STATEMENT[statement];

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

  // Long-tail bucket rows by design hold many source_accounts under the same
  // uni_account (e.g. operating_expense_long_tail = G&A + S&M when SG&A
  // sub-accounts are split by the issuer). Detect those so we sum across
  // children rather than last-write-wins.
  const longTailKeys = new Set(rows.filter((r) => r.kind === "long_tail_bucket").map((r) => r.key));

  // Pivot
  const cellMap: Record<string, Record<string, MatrixCell>> = {};
  for (const row of rows) {
    cellMap[row.key] = {};
    for (const p of periods) {
      cellMap[row.key][p] = { status: "PENDING" };
    }
  }
  // Buffer for long-tail aggregation: [uni_account][period] -> list of children
  const longTailBuf: Record<string, Record<string, Cell[]>> = {};
  for (const c of filtered) {
    if (!cellMap[c.uni_account]) {
      // Not in dictionary — skip (parser produced an unknown uni_account)
      continue;
    }
    if (!cellMap[c.uni_account][c.period]) continue;
    if (longTailKeys.has(c.uni_account)) {
      (longTailBuf[c.uni_account] ??= {})[c.period] ??= [];
      longTailBuf[c.uni_account][c.period].push(c);
    } else {
      cellMap[c.uni_account][c.period] = { cell: c, status: c.status };
    }
  }
  // Aggregate long-tail buckets: sum value * weight; keep child list in provenance.
  // Suppress children whose xbrl_tag rolls up into a core row that already has a
  // populated cell for the same period (double-display avoidance — see
  // `LONG_TAIL_ROLLUP_HINTS` in constants.ts and the SG&A long-tail design note).
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
      if (children.length === 0) {
        // All children rolled up into populated core rows; leave the bucket
        // cell as PENDING ("—") to avoid visually duplicating the core row.
        continue;
      }
      const summed = children.reduce((s, c) => s + c.value * (c.weight ?? 1), 0);
      // Use first child as template for shape; override value + tag + provenance.
      const base = children[0];
      const synthetic: Cell = {
        ...base,
        uni_account: k,
        source_account: children.length === 1 ? base.source_account : "SUM(long_tail)",
        xbrl_tag: null,
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
