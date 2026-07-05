// Ticker discovery grouping — market-aware picker logic, kept as a pure module
// so it is unit-testable in the node environment (no DOM / no fetch). The
// TickerPicker fetches /api/financials/companies and hands the list here; the
// route + picker are the only things that ever touch the network.

// Fallback ticker registry — used when /api/financials/companies is unreachable
// so the US viewer never breaks. Mirrors the pre-onboarded US tickers.
export const KNOWN_TICKERS_FALLBACK = ["AAOI", "INTC", "LITE", "MU", "SNDK"] as const;

export type CompanyListItem = {
  ticker: string;
  company_name: string;
  exchange: string;
};

export type Market = "US" | "TW";

export type TickerGroup = {
  market: Market;
  /** Human-readable group heading for the picker. */
  label: string;
  tickers: CompanyListItem[];
};

// Data-driven market discriminator: TWSE → 台股, everything else → US. Matches
// the storage decision (no `market` column; `exchange` self-describes).
function marketOf(exchange: string): Market {
  return exchange === "TWSE" ? "TW" : "US";
}

const MARKET_LABEL: Record<Market, string> = {
  US: "US",
  TW: "台股",
};

// Group a discovered company list by market (US first, then 台股). Empty groups
// are omitted. When `companies` is null/empty (fetch failed or nothing came
// back) we synthesise a US-only group from KNOWN_TICKERS_FALLBACK so the picker
// always renders the US tickers and never breaks.
export function groupTickersByMarket(
  companies: CompanyListItem[] | null | undefined,
): TickerGroup[] {
  const list =
    companies && companies.length > 0
      ? companies
      : KNOWN_TICKERS_FALLBACK.map((ticker) => ({
          ticker,
          company_name: ticker,
          exchange: "NASDAQ",
        }));

  const byMarket: Record<Market, CompanyListItem[]> = { US: [], TW: [] };
  for (const c of list) {
    byMarket[marketOf(c.exchange)].push(c);
  }

  const order: Market[] = ["US", "TW"];
  const groups: TickerGroup[] = [];
  for (const market of order) {
    const tickers = byMarket[market];
    if (tickers.length === 0) continue;
    tickers.sort((a, b) => a.ticker.localeCompare(b.ticker));
    groups.push({ market, label: MARKET_LABEL[market], tickers });
  }
  return groups;
}
