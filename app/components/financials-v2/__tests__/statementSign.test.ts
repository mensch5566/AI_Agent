import { describe, expect, it } from "vitest";
import { displayValue } from "../StatementMatrix";
import type { Cell } from "../types";

// PDF-faithful sign rendering. `display_negated` (resolved per-fact at upsert from
// the matched XBRL presentation arc's preferred_label "negated…" role) governs the
// displayed sign:
//   - present (non-null) → TRUE negation: display_negated ? -value : value.
//     This is why a stored -26 with display_negated=true renders as +26 (NOT
//     -Math.abs, which the legacy mechanism wrongly used).
//   - null (ticker not yet re-upserted) → fall back to the legacy
//     sign_flip_concepts path so other tickers don't regress.
// The negation happens BEFORE fmtStatementValue, which parenthesizes negatives.

function cell(partial: Partial<Cell>): Cell {
  return {
    ticker: "MU",
    period: "Q2_FY2026",
    period_end: "2026-02-27",
    period_kind: "quarterly",
    statement: "IS",
    version: "GAAP",
    uni_account: "x",
    source_account: "x",
    display_label: null,
    display_negated: null,
    xbrl_tag: null,
    value: 0,
    weight: null,
    unit: "USD_millions",
    status: "SOURCE_OF_TRUTH",
    ordinal: null,
    long_tail_metadata: null,
    provenance: {},
    source_table: "facts",
    ...partial,
  } as Cell;
}

describe("displayValue PDF-faithful sign (display_negated)", () => {
  it("display_negated=true flips a positive stored value to a parenthesized negative", () => {
    // MU IS IncomeTaxExpenseBenefit: stored 2371, negatedLabel → (2,371).
    const c = cell({ value: 2371, display_negated: true });
    expect(displayValue(c, new Set(), "IS")).toBe("(2,371)");
  });

  it("display_negated=true on an already-negative stored value flips it to positive (true negation, not -abs)", () => {
    // MU IS OtherOperatingIncomeExpenseNet: stored -26, negatedLabel → -(-26)=+26.
    // The legacy -Math.abs would have wrongly produced (26); true negation gives 26.
    const c = cell({ value: -26, display_negated: true });
    expect(displayValue(c, new Set(), "IS")).toBe("26");
  });

  it("display_negated=true parenthesizes a BS treasury stock positive (MU TreasuryStockCommonValue)", () => {
    // stored 8502, negatedTerseLabel → (8,502).
    const c = cell({ statement: "BS", value: 8502, display_negated: true });
    expect(displayValue(c, new Set(), "BS")).toBe("(8,502)");
  });

  it("display_negated=false leaves the sign unchanged", () => {
    const c = cell({ value: 13643, display_negated: false });
    expect(displayValue(c, new Set(), "IS")).toBe("13,643");
  });

  it("display_negated=false does NOT consult the legacy sign_flip set", () => {
    // Even if the concept is in the legacy flip set, an explicit false wins.
    const c = cell({ value: 13643, display_negated: false, xbrl_tag: "us-gaap:Foo" });
    expect(displayValue(c, new Set(["us-gaap:Foo"]), "IS")).toBe("13,643");
  });

  it("display_negated=null falls back to the legacy sign_flip path (flip applies)", () => {
    // Legacy -Math.abs behavior preserved for not-yet-re-upserted tickers.
    const c = cell({ value: 100, display_negated: null, xbrl_tag: "us-gaap:Foo" });
    expect(displayValue(c, new Set(["us-gaap:Foo"]), "IS")).toBe("(100)");
  });

  it("display_negated=null with no legacy flip leaves the value as-is", () => {
    const c = cell({ value: 100, display_negated: null, xbrl_tag: "us-gaap:Bar" });
    expect(displayValue(c, new Set(["us-gaap:Foo"]), "IS")).toBe("100");
  });

  it("display_negated=undefined (omitted) also uses the legacy fallback", () => {
    const c = cell({ value: 100, xbrl_tag: "us-gaap:Foo" });
    delete (c as { display_negated?: unknown }).display_negated;
    expect(displayValue(c, new Set(["us-gaap:Foo"]), "IS")).toBe("(100)");
  });
});
