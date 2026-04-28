import YahooFinance from "yahoo-finance2";

export interface PeRawPoint {
  date: string;
  close: number;
  basicEpsTtm: number | null;
  dilutedEpsTtm: number | null;
}

export interface PeHistoryResult {
  ticker: string;
  currency: string | null;
  series: PeRawPoint[];
  note?: string;
}

type FundamentalsRow = {
  date: string | Date;
  basicEPS?: number | null;
  dilutedEPS?: number | null;
};

function normalizeTicker(ticker: string) {
  const upper = ticker.toUpperCase();
  return /^\d+$/.test(upper) ? `${upper}.TW` : upper;
}

function toIsoDate(value: string | Date) {
  const date = value instanceof Date ? value : new Date(value);
  return date.toISOString().slice(0, 10);
}

function buildTtmSeries(
  rows: FundamentalsRow[],
  field: "basicEPS" | "dilutedEPS",
) {
  const ordered = rows
    .map((row) => ({
      date: toIsoDate(row.date),
      eps: typeof row[field] === "number" ? row[field] : null,
    }))
    .filter((row) => row.eps !== null)
    .sort((a, b) => a.date.localeCompare(b.date));

  const result: Array<{ date: string; value: number }> = [];
  for (let i = 3; i < ordered.length; i += 1) {
    const window = ordered.slice(i - 3, i + 1);
    if (window.some((item) => item.eps === null)) continue;
    const value = window.reduce((sum, item) => sum + (item.eps ?? 0), 0);
    result.push({ date: ordered[i].date, value });
  }
  return result;
}

export async function fetchPeHistory(ticker: string): Promise<PeHistoryResult> {
  const yf = new YahooFinance();
  const symbol = normalizeTicker(ticker);
  const endDate = new Date();
  const startDate = new Date(endDate);
  startDate.setFullYear(startDate.getFullYear() - 6);

  const [quote, historical, fundamentals] = await Promise.all([
    yf.quote(symbol),
    yf.historical(symbol, {
      period1: startDate,
      period2: endDate,
      interval: "1d",
    }),
    yf.fundamentalsTimeSeries(symbol, {
      period1: startDate,
      period2: endDate,
      type: "quarterly",
      module: "financials",
    }) as Promise<FundamentalsRow[]>,
  ]);

  const basicTtm = buildTtmSeries(fundamentals ?? [], "basicEPS");
  const dilutedTtm = buildTtmSeries(fundamentals ?? [], "dilutedEPS");
  let basicIdx = 0;
  let dilutedIdx = 0;
  let currentBasic: number | null = null;
  let currentDiluted: number | null = null;

  const series = (historical ?? [])
    .filter((row) => row?.date && typeof row.close === "number")
    .sort((a, b) => a.date.getTime() - b.date.getTime())
    .map((row) => {
      const date = row.date.toISOString().slice(0, 10);

      while (basicIdx < basicTtm.length && basicTtm[basicIdx].date <= date) {
        currentBasic = basicTtm[basicIdx].value;
        basicIdx += 1;
      }
      while (dilutedIdx < dilutedTtm.length && dilutedTtm[dilutedIdx].date <= date) {
        currentDiluted = dilutedTtm[dilutedIdx].value;
        dilutedIdx += 1;
      }

      return {
        date,
        close: row.close,
        basicEpsTtm: currentBasic,
        dilutedEpsTtm: currentDiluted,
      };
    })
    .filter((row) => row.basicEpsTtm !== null || row.dilutedEpsTtm !== null);

  return {
    ticker: symbol,
    currency: quote.currency ?? null,
    series,
    note: series.length
      ? undefined
      : "Insufficient quarterly diluted/basic EPS history to reconstruct historical TTM P/E.",
  };
}
