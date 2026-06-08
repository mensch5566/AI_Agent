import { describe, it, expect } from "vitest";
import { buildMatrix, buildDictionaryMatrix } from "../useFinancialMatrix";
import type { Cell, CellStatus, PeriodKind, Statement, Version } from "../types";

// ---------------------------------------------------------------------------
// Task 11 — data-driven IS/BS/CF row builder.
//
// These tests pin the row-identity contract (spec §P1.2/P2.6/G5/G2):
//   - rows come from DIRECT FACTS only (display-eligible prototypes), not the
//     hardcoded ROWS_BY_STATEMENT list;
//   - rowId = uni_account (core) | uni_account + '|' + source_account (long-tail);
//   - sorted by ordinal asc, nulls last, stable; label = display_label || source_account;
//   - derived single-quarter metrics (derived_q2/q3/q4) attach by uni_account to the
//     display-eligible prototype row — no (uni|null) ghost row;
//   - display-ineligible synthetic SUM core → no prototype, not pulled back by derived;
//   - metric-only rows (ebitda / free_cash_flow) excluded from IS/BS/CF;
//   - period filtering preserved.
// ---------------------------------------------------------------------------

// Build a FACT cell (source_table='facts'): carries source_account + display
// metadata. A display-eligible prototype has display_label and/or ordinal set.
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

// Build a derived/metric cell (source_table='metrics'): no source_account, no
// ordinal, no display_label — attaches to its prototype row by uni_account.
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

describe("buildMatrix — data-driven IS/BS/CF row builder", () => {
  // (1) Row prototypes come from DIRECT FACTS only; a metric-only cell never
  //     creates a row.
  it("builds rows from direct facts, not the hardcoded ROWS list", () => {
    const cells: Cell[] = [
      fact({ uni_account: "revenue", source_account: "Net revenue", display_label: "Net revenue", ordinal: 1, statement: "IS", period: "Q1_FY2025" }),
      fact({ uni_account: "gross_profit", source_account: "Gross margin", display_label: "Gross margin", ordinal: 3, statement: "IS", period: "Q1_FY2025" }),
    ];
    const m = buildMatrix(cells, "IS", GAAP, "quarterly");
    const keys = m.rows.map((r) => r.key);
    // Only the two disclosed rows exist — NOT the full IS_ROWS dictionary.
    expect(keys).toEqual(["revenue", "gross_profit"]);
    // A dictionary row with no fact (e.g. eps_diluted) must NOT appear.
    expect(keys).not.toContain("eps_diluted");
  });

  it("does NOT create a row for a metric-only cell that has no direct fact prototype", () => {
    const cells: Cell[] = [
      fact({ uni_account: "revenue", display_label: "Revenue", ordinal: 1, statement: "IS", period: "Q1_FY2025" }),
      // metric-only, no matching fact prototype
      metric({ uni_account: "net_income_yoy", period: "Q1_FY2025", statement: "IS", period_kind: "quarter_duration" }),
    ];
    const m = buildMatrix(cells, "IS", GAAP, "quarterly");
    expect(m.rows.map((r) => r.key)).toEqual(["revenue"]);
  });

  // (2) rowId: core = uni_account; long-tail bucket member = uni_account|source_account
  it("uses uni_account as rowId for core rows", () => {
    const cells: Cell[] = [
      fact({ uni_account: "revenue", display_label: "Revenue", ordinal: 1, statement: "IS", period: "Q1_FY2025" }),
    ];
    const m = buildMatrix(cells, "IS", GAAP, "quarterly");
    expect(m.rows[0].key).toBe("revenue");
    expect(m.cells["revenue"]["Q1_FY2025"].cell?.value).toBe(100);
  });

  it("uses uni_account|source_account as rowId for long-tail bucket members (disambiguates shared bucket)", () => {
    const cells: Cell[] = [
      fact({ uni_account: "operating_expense_long_tail", source_account: "Restructuring", display_label: "Restructuring", ordinal: 5, value: 10, statement: "IS", period: "Q1_FY2025" }),
      fact({ uni_account: "operating_expense_long_tail", source_account: "Impairment", display_label: "Impairment", ordinal: 6, value: 20, statement: "IS", period: "Q1_FY2025" }),
    ];
    const m = buildMatrix(cells, "IS", GAAP, "quarterly");
    const keys = m.rows.map((r) => r.key);
    expect(keys).toContain("operating_expense_long_tail|Restructuring");
    expect(keys).toContain("operating_expense_long_tail|Impairment");
    // Two distinct rows — NOT collapsed into one by uni_account.
    expect(keys.length).toBe(2);
    expect(m.cells["operating_expense_long_tail|Restructuring"]["Q1_FY2025"].cell?.value).toBe(10);
    expect(m.cells["operating_expense_long_tail|Impairment"]["Q1_FY2025"].cell?.value).toBe(20);
  });

  // (3) Sorted by ordinal asc, nulls last, stable; label = display_label || source_account
  it("sorts rows by ordinal ascending with nulls last, stable", () => {
    const cells: Cell[] = [
      fact({ uni_account: "gross_profit", display_label: "Gross", ordinal: 3, statement: "IS", period: "Q1_FY2025" }),
      fact({ uni_account: "revenue", display_label: "Revenue", ordinal: 1, statement: "IS", period: "Q1_FY2025" }),
      // null-ordinal fact: appended last
      fact({ uni_account: "misc_long_tail", source_account: "OddItem", display_label: "Odd Item", ordinal: null, statement: "IS", period: "Q1_FY2025" }),
      fact({ uni_account: "operating_income", display_label: "Op Inc", ordinal: 2, statement: "IS", period: "Q1_FY2025" }),
    ];
    const m = buildMatrix(cells, "IS", GAAP, "quarterly");
    expect(m.rows.map((r) => r.key)).toEqual([
      "revenue",
      "operating_income",
      "gross_profit",
      "misc_long_tail|OddItem",
    ]);
  });

  it("stable order for equal/both-null ordinals (preserves input order)", () => {
    const cells: Cell[] = [
      fact({ uni_account: "misc_long_tail", source_account: "A", display_label: "A", ordinal: null, statement: "IS", period: "Q1_FY2025" }),
      fact({ uni_account: "misc_long_tail", source_account: "B", display_label: "B", ordinal: null, statement: "IS", period: "Q1_FY2025" }),
    ];
    const m = buildMatrix(cells, "IS", GAAP, "quarterly");
    expect(m.rows.map((r) => r.key)).toEqual(["misc_long_tail|A", "misc_long_tail|B"]);
  });

  it("row label = display_label, falling back to source_account when display_label is null", () => {
    const cells: Cell[] = [
      fact({ uni_account: "revenue", source_account: "Net revenue", display_label: "Net revenue (PDF)", ordinal: 1, statement: "IS", period: "Q1_FY2025" }),
      fact({ uni_account: "cost_of_goods_sold", source_account: "Cost of sales", display_label: null, ordinal: 2, statement: "IS", period: "Q1_FY2025" }),
    ];
    const m = buildMatrix(cells, "IS", GAAP, "quarterly");
    const byKey = Object.fromEntries(m.rows.map((r) => [r.key, r.label]));
    expect(byKey["revenue"]).toBe("Net revenue (PDF)");
    expect(byKey["cost_of_goods_sold"]).toBe("Cost of sales");
  });

  // (4) Deterministic label prototype: when display_label/ordinal vary across
  //     periods for the same core rowId, pick deterministically (highest period),
  //     NOT data iteration order.
  it("deterministic label/ordinal prototype across periods (latest period wins, not input order)", () => {
    const cells: Cell[] = [
      // Older period appears FIRST in input but should NOT win the prototype.
      fact({ uni_account: "revenue", source_account: "Sales", display_label: "Sales", ordinal: 9, statement: "IS", period: "Q1_FY2025" }),
      // Newer period: this label/ordinal must be chosen deterministically.
      fact({ uni_account: "revenue", source_account: "Net revenue", display_label: "Net revenue", ordinal: 1, statement: "IS", period: "Q4_FY2025" }),
    ];
    const m = buildMatrix(cells, "IS", GAAP, "quarterly");
    const row = m.rows.find((r) => r.key === "revenue")!;
    expect(row.label).toBe("Net revenue");
    // ordinal from the latest-period prototype drives sort position too.
    // (single row, but assert the chosen prototype's ordinal by re-running w/ a 2nd row)
    const cells2: Cell[] = [
      ...cells,
      fact({ uni_account: "gross_profit", display_label: "GP", ordinal: 3, statement: "IS", period: "Q4_FY2025" }),
    ];
    const m2 = buildMatrix(cells2, "IS", GAAP, "quarterly");
    // revenue ordinal=1 (from Q4) sorts before gross_profit ordinal=3.
    expect(m2.rows.map((r) => r.key)).toEqual(["revenue", "gross_profit"]);
  });

  // (5) Derived single-quarter attach: ALL of derived_q2/q3/q4 attach by
  //     uni_account to the display-eligible prototype — NO ghost (uni|null) row.
  it("derived_q2/q3/q4 all attach by uni_account to the prototype row (no ghost row)", () => {
    const cells: Cell[] = [
      // direct fact prototype for revenue across the quarters that carry direct facts
      fact({ uni_account: "revenue", display_label: "Revenue", ordinal: 1, value: 100, statement: "IS", period: "Q1_FY2025", period_kind: "quarter_duration" }),
      // derived single-quarter cells (metrics-only, no source_account/ordinal)
      metric({ uni_account: "revenue", period: "Q2_FY2025", statement: "IS", period_kind: "derived_q2", value: 210 }),
      metric({ uni_account: "revenue", period: "Q3_FY2025", statement: "IS", period_kind: "derived_q3", value: 320 }),
      metric({ uni_account: "revenue", period: "Q4_FY2025", statement: "IS", period_kind: "derived_q4", value: 430 }),
    ];
    const m = buildMatrix(cells, "IS", GAAP, "quarterly");
    // Exactly ONE revenue row (the prototype) — no ghost.
    expect(m.rows.map((r) => r.key)).toEqual(["revenue"]);
    // All three derived quarters filled that row's columns.
    expect(m.cells["revenue"]["Q2_FY2025"].cell?.value).toBe(210);
    expect(m.cells["revenue"]["Q3_FY2025"].cell?.value).toBe(320);
    expect(m.cells["revenue"]["Q4_FY2025"].cell?.value).toBe(430);
    // Q1 direct fact still present.
    expect(m.cells["revenue"]["Q1_FY2025"].cell?.value).toBe(100);
  });

  // (6) Display-ineligible synthetic SUM core: no prototype row; derived_q2/q3/q4
  //     for the same uni_account must NOT pull it back into the statement.
  it("display-ineligible synthetic SUM core builds no row, and derived_q2/q3/q4 do not pull it back", () => {
    const cells: Cell[] = [
      fact({ uni_account: "revenue", display_label: "Revenue", ordinal: 1, statement: "IS", period: "Q1_FY2025" }),
      // synthetic SUM core: display_label null, ordinal null, source_account "SUM(...)" → display-ineligible
      fact({ uni_account: "selling_general_administrative", source_account: "SUM(S&M+G&A)", display_label: null, ordinal: null, statement: "IS", period: "Q1_FY2025" }),
      // derived single quarters for the SAME ineligible uni_account
      metric({ uni_account: "selling_general_administrative", period: "Q2_FY2025", statement: "IS", period_kind: "derived_q2", value: 11 }),
      metric({ uni_account: "selling_general_administrative", period: "Q3_FY2025", statement: "IS", period_kind: "derived_q3", value: 12 }),
      metric({ uni_account: "selling_general_administrative", period: "Q4_FY2025", statement: "IS", period_kind: "derived_q4", value: 13 }),
    ];
    const m = buildMatrix(cells, "IS", GAAP, "quarterly");
    const keys = m.rows.map((r) => r.key);
    expect(keys).toEqual(["revenue"]);
    expect(keys).not.toContain("selling_general_administrative");
    // And no ghost row keyed with a null source_account.
    expect(keys).not.toContain("selling_general_administrative|null");
  });

  // (7) Metric-only rows ebitda / free_cash_flow excluded from IS/BS/CF.
  it("excludes ebitda from IS even if a metric cell exists", () => {
    const cells: Cell[] = [
      fact({ uni_account: "net_income", display_label: "Net income", ordinal: 1, statement: "IS", period: "Q1_FY2025" }),
      metric({ uni_account: "ebitda", period: "Q1_FY2025", statement: "IS", period_kind: "quarter_duration", value: 999 }),
    ];
    const m = buildMatrix(cells, "IS", GAAP, "quarterly");
    expect(m.rows.map((r) => r.key)).toEqual(["net_income"]);
    expect(m.rows.map((r) => r.key)).not.toContain("ebitda");
  });

  it("excludes free_cash_flow from CF even if a metric cell exists", () => {
    const cells: Cell[] = [
      fact({ uni_account: "net_cash_from_operating", display_label: "Cash from operations", ordinal: 1, statement: "CF", period: "Q1_FY2025" }),
      metric({ uni_account: "free_cash_flow", period: "Q1_FY2025", statement: "CF", period_kind: "quarter_duration", value: 777 }),
    ];
    const m = buildMatrix(cells, "CF", GAAP, "quarterly");
    expect(m.rows.map((r) => r.key)).toEqual(["net_cash_from_operating"]);
    expect(m.rows.map((r) => r.key)).not.toContain("free_cash_flow");
  });

  // (8) Period filtering preserved.
  it("preserves IS/CF quarterly period filter (quarter_duration ∪ derived_q2/q3/q4)", () => {
    const cells: Cell[] = [
      fact({ uni_account: "revenue", display_label: "Revenue", ordinal: 1, statement: "IS", period: "Q1_FY2025", period_kind: "quarter_duration" }),
      metric({ uni_account: "revenue", period: "Q2_FY2025", statement: "IS", period_kind: "derived_q2", value: 2 }),
      // annual-only duration must NOT appear in quarterly mode
      fact({ uni_account: "revenue", display_label: "Revenue", ordinal: 1, statement: "IS", period: "FY2025", period_kind: "fy_annual_duration", value: 9 }),
    ];
    const m = buildMatrix(cells, "IS", GAAP, "quarterly");
    expect(m.periods).toEqual(["Q1_FY2025", "Q2_FY2025"]);
    expect(m.periods).not.toContain("FY2025");
  });

  it("preserves IS annual period filter (fy_annual_duration only)", () => {
    const cells: Cell[] = [
      fact({ uni_account: "revenue", display_label: "Revenue", ordinal: 1, statement: "IS", period: "FY2025", period_kind: "fy_annual_duration", value: 9 }),
      fact({ uni_account: "revenue", display_label: "Revenue", ordinal: 1, statement: "IS", period: "Q1_FY2025", period_kind: "quarter_duration", value: 1 }),
    ];
    const m = buildMatrix(cells, "IS", GAAP, "annual");
    expect(m.periods).toEqual(["FY2025"]);
  });

  it("preserves BS instant filter + annual Q4-instant→FY remap", () => {
    const cells: Cell[] = [
      // Q4 instant snapshot — in annual mode remapped to FY2025
      fact({ uni_account: "total_assets", display_label: "Total assets", ordinal: 1, statement: "BS", period: "Q4_FY2025", period_kind: "instant_period_end", value: 500 }),
    ];
    const annual = buildMatrix(cells, "BS", GAAP, "annual");
    expect(annual.periods).toEqual(["FY2025"]);
    expect(annual.cells["total_assets"]["FY2025"].cell?.value).toBe(500);

    const quarterly = buildMatrix(cells, "BS", GAAP, "quarterly");
    expect(quarterly.periods).toEqual(["Q4_FY2025"]);
    expect(quarterly.cells["total_assets"]["Q4_FY2025"].cell?.value).toBe(500);
  });
});

describe("buildMatrix — RATIO statement unchanged", () => {
  it("still renders the full RATIO_ROWS dictionary (data-driven change is IS/BS/CF only)", () => {
    const cells: Cell[] = [
      metric({ uni_account: "gross_margin_pct", period: "Q1_FY2025", statement: "RATIO", period_kind: "quarter_duration", value: 0.45 }),
    ];
    const m = buildMatrix(cells, "RATIO", GAAP, "quarterly");
    // RATIO keeps the fixed dictionary order/rows even when most are empty.
    const keys = m.rows.map((r) => r.key);
    expect(keys).toContain("gross_margin_pct");
    expect(keys).toContain("current_ratio");
    expect(keys.length).toBeGreaterThan(10);
    expect(m.cells["gross_margin_pct"]["Q1_FY2025"].cell?.value).toBe(0.45);
  });
});

// ---------------------------------------------------------------------------
// View-mode toggle (PDF-faithful ⇄ uni_account).
// ---------------------------------------------------------------------------
describe("view-mode: uni_account (buildDictionaryMatrix)", () => {
  it("never renders METRIC_ONLY_UNI (ebitda) as an inline IS row", () => {
    const cells = [
      fact({ uni_account: "revenue", source_account: "Revenues", statement: "IS",
             period: "Q2_FY2026", value: 100 }),
      fact({ uni_account: "ebitda", source_account: "EBITDA", statement: "IS",
             period: "Q2_FY2026", value: 40 }),
    ];
    const m = buildDictionaryMatrix(cells, "IS", ["Q2_FY2026"]);
    expect(m.rows.some((r) => r.key === "ebitda")).toBe(false);
    expect(m.rows.some((r) => r.key === "revenue")).toBe(true);
  });

  it("long-tail SUM cell clears display_negated → bucket keeps natural summed sign", () => {
    const cells = [
      fact({ uni_account: "operating_expense_long_tail", source_account: "A", statement: "IS",
             period: "Q2_FY2026", value: 10, weight: 1, display_negated: true,
             long_tail_metadata: { rolls_up_to: "total_operating_expenses" } }),
      fact({ uni_account: "operating_expense_long_tail", source_account: "B", statement: "IS",
             period: "Q2_FY2026", value: 5, weight: 1, display_negated: false,
             long_tail_metadata: { rolls_up_to: "total_operating_expenses" } }),
    ];
    const m = buildDictionaryMatrix(cells, "IS", ["Q2_FY2026"]);
    const mc = m.cells["operating_expense_long_tail"]?.["Q2_FY2026"];
    expect(mc?.cell?.value).toBe(15);
    expect(mc?.cell?.display_negated).toBeNull();
  });
});

describe("view-mode: buildMatrix viewMode routing", () => {
  it("'uni' yields fixed canonical rows; 'pdf' yields data-driven rows", () => {
    const cells = [
      fact({ uni_account: "revenue", source_account: "Revenues", statement: "IS",
             period: "Q2_FY2026", value: 100, display_label: "Net sales", ordinal: 1 }),
    ];
    const uni = buildMatrix(cells, "IS", "GAAP", "quarterly", "uni");
    const pdf = buildMatrix(cells, "IS", "GAAP", "quarterly", "pdf");
    expect(uni.rows.some((r) => r.key === "revenue" && r.label === "Revenue")).toBe(true);
    expect(pdf.rows.some((r) => r.label === "Net sales")).toBe(true);
  });

  it("defaults to pdf when viewMode omitted (back-compat 4-arg arity)", () => {
    const cells = [
      fact({ uni_account: "revenue", source_account: "Revenues", statement: "IS",
             period: "Q2_FY2026", value: 100, display_label: "Net sales", ordinal: 1 }),
    ];
    const def = buildMatrix(cells, "IS", "GAAP", "quarterly");
    expect(def.rows.some((r) => r.label === "Net sales")).toBe(true);
  });
});
