import { NextResponse } from "next/server";
import { createServerClient } from "@/lib/supabase";

// Hardcoded tickers for each market
const MARKET_TICKERS = {
  us: ["SPY", "QQQ", "DIA"],
  tw: ["0050.TW", "0051.TW"],
};

// Use dynamic import to avoid loading yfinance at build time if not needed
async function fetchYahooFinanceData(
  ticker: string,
  days: number = 3
): Promise<{ date: string; open: number; high: number; low: number; close: number; volume: number }[]> {
  // Dynamic import of yfinance alternative
  // Using yahoo-finance2 npm package (lightweight Node.js alternative)
  const yf = await import("yahoo-finance2").then(m => m.default);

  const endDate = new Date();
  const startDate = new Date(endDate);
  startDate.setDate(startDate.getDate() - days);

  try {
    const quotes = await yf.quote(ticker);
    if (!quotes) {
      return [];
    }

    const historical: any[] = await yf.historical(ticker, {
      period1: startDate,
      period2: endDate,
    });

    return (historical || []).map((quote: any) => ({
      date: quote.date.toISOString().split('T')[0],
      open: parseFloat(quote.open.toFixed(4)),
      high: parseFloat(quote.high.toFixed(4)),
      low: parseFloat(quote.low.toFixed(4)),
      close: parseFloat(quote.close.toFixed(4)),
      volume: Math.floor(quote.volume),
    }));
  } catch (err) {
    console.error(`Failed to fetch ${ticker}:`, err);
    return [];
  }
}

export async function GET(req: Request) {
  const url = new URL(req.url);
  const market = url.searchParams.get("market") as "us" | "tw" | null;

  // Verify authorization
  const authHeader = req.headers.get("authorization");
  const cronSecret = process.env.CRON_SECRET;
  if (cronSecret && authHeader !== `Bearer ${cronSecret}`) {
    return NextResponse.json(
      { error: "Unauthorized" },
      { status: 401 }
    );
  }

  if (!market || !["us", "tw"].includes(market)) {
    return NextResponse.json(
      { error: "Invalid market. Use ?market=us or ?market=tw" },
      { status: 400 }
    );
  }

  const tickers = MARKET_TICKERS[market];
  const supabase = createServerClient();
  const updated: Array<{ ticker: string; date: string; close: number }> = [];
  const skipped: string[] = [];

  try {
    for (const ticker of tickers) {
      const priceData = await fetchYahooFinanceData(ticker, 3);

      if (priceData.length === 0) {
        skipped.push(`${ticker} (no data)`);
        continue;
      }

      // Upsert data
      const upsertData = priceData.map(p => ({
        ticker,
        date: p.date,
        open: p.open,
        high: p.high,
        low: p.low,
        close: p.close,
        volume: p.volume,
      }));

      const { error } = await supabase
        .from("stock_prices")
        .upsert(upsertData, { onConflict: "ticker,date" });

      if (error) {
        skipped.push(`${ticker} (${error.message})`);
      } else {
        // Track the latest update
        const latest = priceData[priceData.length - 1];
        updated.push({
          ticker,
          date: latest.date,
          close: latest.close,
        });
      }
    }

    return NextResponse.json({
      market,
      updated,
      skipped,
      timestamp: new Date().toISOString(),
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json(
      {
        error: message,
        market,
      },
      { status: 500 }
    );
  }
}
