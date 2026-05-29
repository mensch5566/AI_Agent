// Default Financials landing — list available tickers.

import Link from "next/link";
import ThemeToggle from "@/app/components/ThemeToggle";
import { KNOWN_TICKERS } from "@/app/components/financials-v2/constants";
import { Button } from "@/components/ui/button";

export default function FinancialsLandingPage() {
  return (
    <main className="max-w-screen-md mx-auto p-6 text-foreground">
      <div className="flex items-start justify-between mb-4">
        <h1 className="text-2xl font-semibold">Financials Viewer</h1>
        <ThemeToggle />
      </div>
      <p className="text-sm mb-4 text-muted-foreground">Select a ticker:</p>
      <div className="flex flex-wrap gap-2">
        {KNOWN_TICKERS.map((t) => (
          <Button key={t} variant="outline" asChild>
            <Link href={`/financials/${t}`}>{t}</Link>
          </Button>
        ))}
      </div>
    </main>
  );
}
