import { describe, it, expect } from "vitest";
import {
  KNOWN_TICKERS,
  DERIVED_NONGAAP_ABSOLUTE_ROWS,
} from "../constants";
import { buildDerivedNonGaapRows } from "../useFinancialMatrix";
import { buildMatrix } from "../useFinancialMatrix";
import type { Cell, CellStatus, PeriodKind, Statement, Version } from "../types";

// ---------------------------------------------------------------------------
// Task 13 — Derived / Non-GAAP absolute-value subsection (ebitda + free_cash_flow)
// + KNOWN_TICKERS += MU.
//
// ebitda (statement=IS, source_table=metrics) and free_cash_flow (statement=CF,
// source_table=metrics) are $ absolute-value derived rows. Earlier tasks made
// them METRIC_ONLY_UNI so they NEVER render inline in the IS/CF statements, and
// they are NOT in RATIO_ROWS — so they cannot reach the user via either path.
// buildDerivedNonGaapRows() is the pure selector that surfaces them in the
// Derived/Non-GAAP subsection of the analytics area, formatted as $ values.
// ---------------------------------------------------------------------------

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
    unit: partial.unit ?? "USD_millions",
    status: (partial.status ?? "DERIVED_FROM_DISCLOSED") as CellStatus,
    ordinal: null,
    long_tail_metadata: null,
    provenance: partial.provenance ?? {},
    source_table: "metrics",
  };
}

const GAAP: Version = "GAAP";

describe("Task 13 — KNOWN_TICKERS + DERIVED_NONGAAP_ABSOLUTE_ROWS constants", () => {
  it("KNOWN_TICKERS includes MU and still includes the original four", () => {
    expect(KNOWN_TICKERS).toContain("MU");
    for (const t of ["AAOI", "INTC", "LITE", "SNDK"]) {
      expect(KNOWN_TICKERS).toContain(t);
    }
    // 4 original + MU = 5
    expect(KNOWN_TICKERS.length).toBe(5);
  });

  it("DERIVED_NONGAAP_ABSOLUTE_ROWS equals ['ebitda','free_cash_flow']", () => {
    expect([...DERIVED_NONGAAP_ABSOLUTE_ROWS]).toEqual([
      "ebitda",
      "free_cash_flow",
    ]);
  });
});

describe("buildDerivedNonGaapRows — Derived/Non-GAAP $ subsection selector", () => {
  it("picks up ebitda (IS) and free_cash_flow (CF) metric cells", () => {
    const cells: Cell[] = [
      metric({ uni_account: "ebitda", statement: "IS", period: "Q1_FY2025", period_kind: "quarter_duration", value: 1000 }),
      metric({ uni_account: "free_cash_flow", statement: "CF", period: "Q1_FY2025", period_kind: "quarter_duration", value: 250 }),
    ];
    const m = buildDerivedNonGaapRows(cells, GAAP, "quarterly");

    expect(m.rows.map((r) => r.key)).toEqual(["ebitda", "free_cash_flow"]);
    expect(m.periods).toEqual(["Q1_FY2025"]);
    expect(m.cells["ebitda"]["Q1_FY2025"].cell?.value).toBe(1000);
    expect(m.cells["free_cash_flow"]["Q1_FY2025"].cell?.value).toBe(250);
  });

  it("honors the canonical DERIVED_NONGAAP_ABSOLUTE_ROWS order even if cells arrive reversed", () => {
    const cells: Cell[] = [
      metric({ uni_account: "free_cash_flow", statement: "CF", period: "Q1_FY2025", period_kind: "quarter_duration" }),
      metric({ uni_account: "ebitda", statement: "IS", period: "Q1_FY2025", period_kind: "quarter_duration" }),
    ];
    const m = buildDerivedNonGaapRows(cells, GAAP, "quarterly");
    expect(m.rows.map((r) => r.key)).toEqual(["ebitda", "free_cash_flow"]);
  });

  it("attaches derived single-quarter ebitda (derived_q4) in quarterly mode", () => {
    const cells: Cell[] = [
      metric({ uni_account: "ebitda", statement: "IS", period: "Q4_FY2025", period_kind: "derived_q4", value: 1500 }),
    ];
    const m = buildDerivedNonGaapRows(cells, GAAP, "quarterly");
    expect(m.cells["ebitda"]["Q4_FY2025"].cell?.value).toBe(1500);
  });

  it("annual mode picks fy_annual_duration, not quarter cells", () => {
    const cells: Cell[] = [
      metric({ uni_account: "ebitda", statement: "IS", period: "Q1_FY2025", period_kind: "quarter_duration", value: 100 }),
      metric({ uni_account: "ebitda", statement: "IS", period: "FY2025", period_kind: "fy_annual_duration", value: 9000 }),
      metric({ uni_account: "free_cash_flow", statement: "CF", period: "FY2025", period_kind: "fy_annual_duration", value: 3000 }),
    ];
    const m = buildDerivedNonGaapRows(cells, GAAP, "annual");
    expect(m.periods).toEqual(["FY2025"]);
    expect(m.cells["ebitda"]["FY2025"].cell?.value).toBe(9000);
    expect(m.cells["free_cash_flow"]["FY2025"].cell?.value).toBe(3000);
  });

  it("respects version (NON_GAAP cells excluded from the GAAP subsection)", () => {
    const cells: Cell[] = [
      metric({ uni_account: "ebitda", statement: "IS", period: "Q1_FY2025", period_kind: "quarter_duration", version: "NON_GAAP", value: 1 }),
    ];
    const m = buildDerivedNonGaapRows(cells, GAAP, "quarterly");
    // version mismatch → no cell, but the row still exists (continuity) as PENDING
    expect(m.cells["ebitda"]["Q1_FY2025"]).toBeUndefined();
    expect(m.periods).toEqual([]);
  });
});

describe("Derived rows are EXCLUDED from the plain RATIO and IS/CF matrices", () => {
  it("ebitda/free_cash_flow metric cells never appear in the RATIO matrix", () => {
    const cells: Cell[] = [
      // RATIO matrix only collects statement=RATIO cells; these are IS/CF metrics.
      metric({ uni_account: "ebitda", statement: "IS", period: "Q1_FY2025", period_kind: "quarter_duration" }),
      metric({ uni_account: "free_cash_flow", statement: "CF", period: "Q1_FY2025", period_kind: "quarter_duration" }),
    ];
    const ratio = buildMatrix(cells, "RATIO", GAAP, "quarterly");
    expect(ratio.rows.find((r) => r.key === "ebitda")).toBeUndefined();
    expect(ratio.rows.find((r) => r.key === "free_cash_flow")).toBeUndefined();
  });

  it("ebitda/free_cash_flow do not create rows in the IS/CF statement matrices", () => {
    const isMatrix = buildMatrix(
      [metric({ uni_account: "ebitda", statement: "IS", period: "Q1_FY2025", period_kind: "quarter_duration" })],
      "IS",
      GAAP,
      "quarterly",
    );
    expect(isMatrix.rows.find((r) => r.key === "ebitda")).toBeUndefined();

    const cfMatrix = buildMatrix(
      [metric({ uni_account: "free_cash_flow", statement: "CF", period: "Q1_FY2025", period_kind: "quarter_duration" })],
      "CF",
      GAAP,
      "quarterly",
    );
    expect(cfMatrix.rows.find((r) => r.key === "free_cash_flow")).toBeUndefined();
  });
});
