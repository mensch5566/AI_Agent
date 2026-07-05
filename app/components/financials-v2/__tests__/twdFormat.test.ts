import { describe, expect, it } from "vitest";
import { fmtStatementValue } from "../statementFormat";
import { fmtValue } from "../constants";

// Phase E — Taiwan (TWSE / TWD / IFRS) rendering support.
//
// TW money uses the same scale-encoded, PDF-faithful formatting as US: the
// cell `unit` carries the scale (TWD_thousands / TWD_millions) and the currency
// is conveyed at the column/header level, so the statement body shows bare
// numbers exactly like USD. Per-share values are the exception: they carry the
// NT$ symbol (parallel to US $).
describe("fmtStatementValue — TWD money units", () => {
  it("formats TWD_millions as a whole number with thousands separators", () => {
    expect(fmtStatementValue(13643, "TWD_millions")).toBe("13,643");
  });

  it("formats TWD_thousands as a whole number with thousands separators", () => {
    expect(fmtStatementValue(1234567, "TWD_thousands")).toBe("1,234,567");
  });

  it("wraps negative TWD money in parentheses", () => {
    expect(fmtStatementValue(-4370, "TWD_millions")).toBe("(4,370)");
  });

  it("rounds fractional TWD money to a whole number", () => {
    expect(fmtStatementValue(13642.6, "TWD_millions")).toBe("13,643");
  });

  it("formats TWD_per_share to 2 decimals", () => {
    expect(fmtStatementValue(1.5, "TWD_per_share")).toBe("1.50");
  });

  it("wraps negative TWD_per_share in parentheses with 2 decimals", () => {
    expect(fmtStatementValue(-0.23, "TWD_per_share")).toBe("(0.23)");
  });

  it("returns empty string for null/undefined TWD", () => {
    expect(fmtStatementValue(null, "TWD_millions")).toBe("");
    expect(fmtStatementValue(undefined, "TWD_per_share")).toBe("");
  });
});

describe("fmtValue — TWD units", () => {
  it("formats TWD_per_share with NT$ prefix and 2 decimals", () => {
    expect(fmtValue(3.21, "TWD_per_share")).toBe("NT$3.21");
  });

  it("formats TWD_thousands identically to USD_thousands (bare number)", () => {
    expect(fmtValue(2500, "TWD_thousands")).toBe(fmtValue(2500, "USD_thousands"));
    expect(fmtValue(500, "TWD_thousands")).toBe(fmtValue(500, "USD_thousands"));
  });

  it("formats TWD_millions identically to USD_millions (bare number)", () => {
    expect(fmtValue(1234.5, "TWD_millions")).toBe(fmtValue(1234.5, "USD_millions"));
  });
});
