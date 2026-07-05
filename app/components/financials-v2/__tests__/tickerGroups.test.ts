import { describe, expect, it } from "vitest";
import { groupTickersByMarket, KNOWN_TICKERS_FALLBACK } from "../tickerGroups";
import type { CompanyListItem } from "../tickerGroups";

// Phase E — ticker discovery grouping. The picker fetches /api/financials/companies
// and groups by market (US = non-TWSE, 台股 = exchange === "TWSE"). If the fetch
// fails the caller passes null and we fall back to KNOWN_TICKERS so US never breaks.
describe("groupTickersByMarket", () => {
  const companies: CompanyListItem[] = [
    { ticker: "AAOI", company_name: "Applied Optoelectronics", exchange: "NASDAQ" },
    { ticker: "INTC", company_name: "Intel", exchange: "NASDAQ" },
    { ticker: "3081", company_name: "聯亞", exchange: "TWSE" },
    { ticker: "2308", company_name: "台達電", exchange: "TWSE" },
  ];

  it("splits US (non-TWSE) and 台股 (TWSE) into separate groups", () => {
    const groups = groupTickersByMarket(companies);
    const us = groups.find((g) => g.market === "US")!;
    const tw = groups.find((g) => g.market === "TW")!;
    expect(us.tickers.map((t) => t.ticker)).toEqual(["AAOI", "INTC"]);
    expect(tw.tickers.map((t) => t.ticker)).toEqual(["2308", "3081"]);
  });

  it("US group comes before 台股 group", () => {
    const groups = groupTickersByMarket(companies);
    expect(groups.map((g) => g.market)).toEqual(["US", "TW"]);
  });

  it("orders tickers within each group alphabetically/numerically", () => {
    const shuffled: CompanyListItem[] = [
      { ticker: "MU", company_name: "Micron", exchange: "NASDAQ" },
      { ticker: "AAOI", company_name: "AAOI", exchange: "NASDAQ" },
      { ticker: "3081", company_name: "聯亞", exchange: "TWSE" },
    ];
    const groups = groupTickersByMarket(shuffled);
    expect(groups.find((g) => g.market === "US")!.tickers.map((t) => t.ticker)).toEqual([
      "AAOI",
      "MU",
    ]);
  });

  it("omits an empty group entirely (US-only list yields no 台股 group)", () => {
    const usOnly: CompanyListItem[] = [
      { ticker: "AAOI", company_name: "AAOI", exchange: "NASDAQ" },
    ];
    const groups = groupTickersByMarket(usOnly);
    expect(groups.map((g) => g.market)).toEqual(["US"]);
  });

  it("falls back to KNOWN_TICKERS_FALLBACK when list is null (fetch failed)", () => {
    const groups = groupTickersByMarket(null);
    const us = groups.find((g) => g.market === "US")!;
    expect(us.tickers.map((t) => t.ticker)).toEqual([...KNOWN_TICKERS_FALLBACK]);
    // Fallback is US-only so the 台股 group is absent, never breaking US.
    expect(groups.map((g) => g.market)).toEqual(["US"]);
  });

  it("falls back when list is empty", () => {
    const groups = groupTickersByMarket([]);
    expect(groups.find((g) => g.market === "US")!.tickers.map((t) => t.ticker)).toEqual([
      ...KNOWN_TICKERS_FALLBACK,
    ]);
  });
});
