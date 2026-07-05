import { describe, expect, it } from "vitest";
import { BS_ROWS, ROWS_BY_STATEMENT } from "../constants";

// Phase E — Taiwan equity rows (IFRS: legal reserve + NCI family) inserted into
// the shared Balance Sheet row order. US pages have no data for these keys, so
// they render empty/hidden — the ordering here is the only contract that matters.
describe("BS_ROWS TW equity rows", () => {
  const keys = BS_ROWS.map((r) => r.key);

  it("includes the 3 TW equity keys", () => {
    expect(keys).toContain("legal_reserve");
    expect(keys).toContain("minority_interest_bs");
    expect(keys).toContain("total_equity_incl_nci");
  });

  it("places legal_reserve immediately after retained_earnings", () => {
    expect(keys.indexOf("legal_reserve")).toBe(keys.indexOf("retained_earnings") + 1);
  });

  it("places minority_interest_bs and total_equity_incl_nci after total_equity, before total_liabilities_and_equity", () => {
    const te = keys.indexOf("total_equity");
    expect(keys.indexOf("minority_interest_bs")).toBe(te + 1);
    expect(keys.indexOf("total_equity_incl_nci")).toBe(te + 2);
    expect(keys.indexOf("total_liabilities_and_equity")).toBe(te + 3);
  });

  it("assigns the correct MetricSpec shape/kind/label", () => {
    const legal = BS_ROWS.find((r) => r.key === "legal_reserve")!;
    const nci = BS_ROWS.find((r) => r.key === "minority_interest_bs")!;
    const teNci = BS_ROWS.find((r) => r.key === "total_equity_incl_nci")!;
    expect(legal.kind).toBe("core");
    expect(legal.label).toBe("法定盈餘公積");
    expect(nci.kind).toBe("core");
    expect(nci.label).toBe("非控制權益 / Minority Interest");
    expect(teNci.kind).toBe("subtotal");
    expect(teNci.label).toBe("權益總額（含非控制）/ Total Equity incl. NCI");
  });

  it("net_income_nci already exists once and is not duplicated", () => {
    const is = ROWS_BY_STATEMENT.IS.map((r) => r.key);
    expect(is.filter((k) => k === "net_income_nci")).toHaveLength(1);
  });

  it("ROWS_BY_STATEMENT.BS is the updated BS_ROWS", () => {
    expect(ROWS_BY_STATEMENT.BS).toBe(BS_ROWS);
    expect(ROWS_BY_STATEMENT.BS.map((r) => r.key)).toContain("legal_reserve");
  });
});
