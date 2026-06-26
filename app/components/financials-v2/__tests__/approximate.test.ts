import { describe, it, expect } from "vitest";
import { buildMatrix } from "../useFinancialMatrix";
import { approximationTooltip, APPROX_TOOLTIP_FALLBACK } from "../StatementMatrix";
import type { Cell, CellStatus, PeriodKind, Statement } from "../types";

// ---------------------------------------------------------------------------
// provenance.is_approximate marker (†).
//
// Backend now emits approximate Q4 GAAP EPS cells (derive-base FY − Q1 − Q2 − Q3)
// with provenance.is_approximate === true (status DERIVED_FROM_DISCLOSED,
// rule_id Q4_EPS_APPROX_FY_MINUS_Q1Q2Q3). The viewer threads an `isApproximate`
// flag onto the MatrixCell so the render layer can append a superscript dagger
// + tooltip (reason + formula). Non-approximate cells are untouched.
// ---------------------------------------------------------------------------

function fact(partial: Partial<Cell> & {
  uni_account: string;
  period: string;
  statement: Statement;
}): Cell {
  return {
    ticker: "TEST",
    period: partial.period,
    period_end: partial.period_end ?? "2025-12-31",
    period_kind: partial.period_kind ?? "quarter_duration",
    statement: partial.statement,
    version: partial.version ?? "GAAP",
    uni_account: partial.uni_account,
    source_account: partial.source_account ?? null,
    display_label: partial.display_label ?? null,
    xbrl_tag: partial.xbrl_tag ?? null,
    value: partial.value ?? 100,
    weight: partial.weight ?? 1,
    unit: partial.unit ?? "USD_millions",
    status: (partial.status ?? "SOURCE_OF_TRUTH") as CellStatus,
    ordinal: partial.ordinal ?? null,
    display_negated: partial.display_negated ?? null,
    long_tail_metadata: partial.long_tail_metadata ?? null,
    provenance: partial.provenance ?? {},
    source_table: "facts",
  };
}

function metric(partial: Partial<Cell> & {
  uni_account: string;
  period: string;
  statement: Statement;
  period_kind: PeriodKind;
}): Cell {
  return {
    ticker: "TEST",
    period: partial.period,
    period_end: partial.period_end ?? "2025-12-31",
    period_kind: partial.period_kind,
    statement: partial.statement,
    version: partial.version ?? "GAAP",
    uni_account: partial.uni_account,
    source_account: null,
    display_label: null,
    xbrl_tag: null,
    value: partial.value ?? 50,
    weight: null,
    unit: partial.unit ?? "USD_per_share",
    status: (partial.status ?? "DERIVED_FROM_DISCLOSED") as CellStatus,
    ordinal: null,
    display_negated: null,
    long_tail_metadata: null,
    provenance: partial.provenance ?? {},
    source_table: "metrics",
  };
}

describe("buildMatrix — provenance.is_approximate threads onto MatrixCell", () => {
  it("sets isApproximate=true on the derived Q4 EPS cell that carries provenance.is_approximate", () => {
    const cells: Cell[] = [
      // Direct face-statement EPS prototype (Q1) so the row exists.
      fact({
        uni_account: "eps_diluted", source_account: "Diluted EPS",
        display_label: "Diluted EPS", ordinal: 30, unit: "USD_per_share",
        value: 1.1, statement: "IS", period: "Q1_FY2025",
        period_kind: "quarter_duration",
      }),
      // Approximate derived Q4 EPS metric.
      metric({
        uni_account: "eps_diluted", period: "Q4_FY2025", statement: "IS",
        period_kind: "derived_q4", unit: "USD_per_share", value: 0.9,
        provenance: {
          is_approximate: true,
          approximation_reason: "Q4 weighted-share count differs from FY",
          formula: "FY − Q1 − Q2 − Q3",
          rule_id: "Q4_EPS_APPROX_FY_MINUS_Q1Q2Q3",
        },
      }),
    ];
    const m = buildMatrix(cells, "IS", "GAAP", "quarterly");
    expect(m.cells["eps_diluted"]["Q4_FY2025"].cell?.value).toBe(0.9);
    expect(m.cells["eps_diluted"]["Q4_FY2025"].isApproximate).toBe(true);
    // The directly-disclosed Q1 cell is NOT approximate.
    expect(m.cells["eps_diluted"]["Q1_FY2025"].isApproximate).toBeFalsy();
  });

  it("leaves isApproximate falsy for a normal direct fact cell", () => {
    const cells: Cell[] = [
      fact({
        uni_account: "revenue", display_label: "Revenue", ordinal: 1,
        statement: "IS", period: "Q1_FY2025",
      }),
    ];
    const m = buildMatrix(cells, "IS", "GAAP", "quarterly");
    expect(m.cells["revenue"]["Q1_FY2025"].isApproximate).toBeFalsy();
  });
});

describe("approximationTooltip", () => {
  it("composes reason + formula from provenance", () => {
    const c = metric({
      uni_account: "eps_basic", period: "Q4_FY2025", statement: "IS",
      period_kind: "derived_q4", unit: "USD_per_share", value: 0.9,
      provenance: {
        is_approximate: true,
        approximation_reason: "近似值：Q4 加權股數非加性",
        formula: "FY − Q1 − Q2 − Q3",
      },
    });
    expect(approximationTooltip(c)).toBe("近似值：Q4 加權股數非加性 (FY − Q1 − Q2 − Q3)");
  });

  it("falls back to a static string when reason/formula are missing", () => {
    const c = metric({
      uni_account: "eps_basic", period: "Q4_FY2025", statement: "IS",
      period_kind: "derived_q4", unit: "USD_per_share", value: 0.9,
      provenance: { is_approximate: true },
    });
    expect(approximationTooltip(c)).toBe(APPROX_TOOLTIP_FALLBACK);
  });

  it("uses formula-only or reason-only when just one is present", () => {
    const reasonOnly = metric({
      uni_account: "eps_basic", period: "Q4_FY2025", statement: "IS",
      period_kind: "derived_q4", value: 0.9,
      provenance: { is_approximate: true, approximation_reason: "近似值" },
    });
    expect(approximationTooltip(reasonOnly)).toBe("近似值");
    const formulaOnly = metric({
      uni_account: "eps_basic", period: "Q4_FY2025", statement: "IS",
      period_kind: "derived_q4", value: 0.9,
      provenance: { is_approximate: true, formula: "FY − Q1 − Q2 − Q3" },
    });
    expect(approximationTooltip(formulaOnly)).toBe("FY − Q1 − Q2 − Q3");
  });
});
