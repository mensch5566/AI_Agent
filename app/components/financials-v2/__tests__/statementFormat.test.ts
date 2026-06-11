import { describe, expect, it } from "vitest";
import { fmtStatementValue } from "../statementFormat";

// fmtStatementValue is the STATEMENT-SCOPED formatter for the IS/BS/CF table —
// PDF-faithful: $ money as whole numbers with thousands separators (no decimals),
// negatives in parentheses; EPS to 2 decimals (also parenthesized when negative).
// The Ratios view keeps its own (fmtValue) formatter and is unaffected.
describe("fmtStatementValue", () => {
  it("formats USD_millions as a whole number with thousands separators", () => {
    expect(fmtStatementValue(13643, "USD_millions")).toBe("13,643");
  });

  it("wraps negative money in parentheses", () => {
    expect(fmtStatementValue(-4370, "USD_millions")).toBe("(4,370)");
  });

  it("formats EPS (USD_per_share) to 2 decimals", () => {
    expect(fmtStatementValue(1.5, "USD_per_share")).toBe("1.50");
  });

  it("wraps negative EPS in parentheses with 2 decimals", () => {
    expect(fmtStatementValue(-0.23, "USD_per_share")).toBe("(0.23)");
  });

  it("formats thousands-scale money with separators too", () => {
    expect(fmtStatementValue(1234567, "USD_thousands")).toBe("1,234,567");
  });

  it("rounds fractional money to a whole number", () => {
    expect(fmtStatementValue(13642.6, "USD_millions")).toBe("13,643");
  });

  it("returns an empty string for null/undefined", () => {
    expect(fmtStatementValue(null, "USD_millions")).toBe("");
    expect(fmtStatementValue(undefined, "USD_per_share")).toBe("");
  });
});
