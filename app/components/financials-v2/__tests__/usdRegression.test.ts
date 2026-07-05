import { describe, expect, it } from "vitest";
import { fmtStatementValue } from "../statementFormat";
import { fmtValue } from "../constants";

// Phase E zero-regression guard. Adding TWD support must NOT change ANY existing
// USD output. These are the exact strings the US viewer produces today; they are
// frozen here so a future currency edit that touches the USD branches fails loud.
describe("USD output is byte-identical after TWD support", () => {
  const moneyCases: Array<[number, string]> = [
    [13643, "USD_millions"],
    [-4370, "USD_millions"],
    [13642.6, "USD_millions"],
    [1234567, "USD_thousands"],
    [999, "USD_thousands"],
    [0, "USD_millions"],
  ];

  it("fmtStatementValue USD money frozen", () => {
    expect(fmtStatementValue(13643, "USD_millions")).toBe("13,643");
    expect(fmtStatementValue(-4370, "USD_millions")).toBe("(4,370)");
    expect(fmtStatementValue(13642.6, "USD_millions")).toBe("13,643");
    expect(fmtStatementValue(1234567, "USD_thousands")).toBe("1,234,567");
  });

  it("fmtStatementValue USD_per_share frozen", () => {
    expect(fmtStatementValue(1.5, "USD_per_share")).toBe("1.50");
    expect(fmtStatementValue(-0.23, "USD_per_share")).toBe("(0.23)");
  });

  it("fmtStatementValue returns null for non-owned units (unchanged)", () => {
    expect(fmtStatementValue(0.48, "Pure")).toBeNull();
    expect(fmtStatementValue(123, "millions_shares")).toBeNull();
  });

  it("fmtValue USD_per_share frozen ($ prefix, 2dp)", () => {
    expect(fmtValue(3.21, "USD_per_share")).toBe("$3.21");
  });

  it("fmtValue USD_thousands frozen", () => {
    expect(fmtValue(2500, "USD_thousands")).toBe("2.5M");
    expect(fmtValue(500, "USD_thousands")).toBe("500.0K");
  });

  it("fmtValue USD_millions frozen", () => {
    expect(fmtValue(1234.5, "USD_millions")).toBe("1234.5M");
  });

  it("fmtValue Pure ratios/multiples/days frozen", () => {
    expect(fmtValue(0.4814, "Pure")).toBe("48.1%");
    expect(fmtValue(2.19, "Pure", "current_ratio")).toBe("2.19x");
    expect(fmtValue(49.3, "Pure", "dso")).toBe("49.3 days");
  });

  it("fmtValue share units frozen", () => {
    expect(fmtValue(1234.5, "millions_shares")).toBe("1234.5M");
    expect(fmtValue(2500, "thousands_shares")).toBe("2.5M");
  });

  it("USD money never returns null and never varies with TWD present", () => {
    for (const [v, u] of moneyCases) {
      expect(fmtStatementValue(v, u)).not.toBeNull();
    }
  });
});
