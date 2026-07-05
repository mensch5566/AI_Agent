// Default Financials landing — list available tickers, grouped by market.
//
// Discovers onboarded tickers from sec_financial_companies (server-side) and
// groups them by market via `exchange` (US / 台股). Falls back to the static
// KNOWN_TICKERS registry if discovery fails, so the US list never breaks.

import Link from "next/link";
import ThemeToggle from "@/app/components/ThemeToggle";
import { createServerClient } from "@/lib/supabase";
import { groupTickersByMarket } from "@/app/components/financials-v2/tickerGroups";
import type { CompanyListItem } from "@/app/components/financials-v2/tickerGroups";
import { Button } from "@/components/ui/button";

export const dynamic = "force-dynamic";

async function discoverCompanies(): Promise<CompanyListItem[] | null> {
  try {
    const supabase = createServerClient();
    const { data, error } = await supabase
      .from("sec_financial_companies")
      .select("ticker, company_name, exchange")
      .order("ticker", { ascending: true });
    if (error || !data) return null;
    return data.map((c) => ({
      ticker: c.ticker,
      company_name: c.company_name ?? c.ticker,
      exchange: c.exchange ?? "NASDAQ",
    }));
  } catch {
    return null;
  }
}

export default async function FinancialsLandingPage() {
  const companies = await discoverCompanies();
  const groups = groupTickersByMarket(companies);

  return (
    <main className="max-w-screen-md mx-auto p-6 text-foreground">
      <div className="flex items-start justify-between mb-4">
        <h1 className="text-2xl font-semibold">Financials Viewer</h1>
        <ThemeToggle />
      </div>
      <p className="text-sm mb-4 text-muted-foreground">Select a ticker:</p>
      <div className="space-y-4">
        {groups.map((g) => (
          <div key={g.market}>
            <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">
              {g.label}
            </div>
            <div className="flex flex-wrap gap-2">
              {g.tickers.map((t) => (
                <Button key={t.ticker} variant="outline" asChild>
                  <Link href={`/financials/${t.ticker}`}>{t.ticker}</Link>
                </Button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </main>
  );
}
