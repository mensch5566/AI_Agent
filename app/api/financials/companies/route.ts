import { NextResponse } from "next/server";
import { createServerClient } from "@/lib/supabase";

/**
 * SEC Financials v2 — company discovery API.
 *
 * Returns the onboarded tickers from sec_financial_companies so the frontend
 * picker can render dynamically (grouped by market via `exchange`) instead of a
 * hardcoded list. Market-agnostic: US (SEC) and TW (TWSE) companies live in the
 * same table, discriminated by `exchange` / `currency`.
 *
 * Shape: [{ ticker, company_name, exchange }] ordered by ticker.
 */

type CompanyRow = {
  ticker: string;
  company_name: string | null;
  exchange: string | null;
};

export async function GET() {
  const supabase = createServerClient();

  const { data, error } = await supabase
    .from("sec_financial_companies")
    .select("ticker, company_name, exchange")
    .order("ticker", { ascending: true });

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  const companies = (data ?? []).map((c: CompanyRow) => ({
    ticker: c.ticker,
    company_name: c.company_name ?? c.ticker,
    exchange: c.exchange ?? "NASDAQ",
  }));

  return NextResponse.json({ companies });
}
