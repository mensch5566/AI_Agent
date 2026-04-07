import { useState, useEffect } from "react";
import { FactStore, type FactRow, type CompanyInfo } from "./FactStore";

interface ApiResponse {
  ticker: string;
  company: CompanyInfo | null;
  facts: FactRow[];
}

/* ================================================================
   Data fetching hook — returns FactStore
   ================================================================ */

const cache = new Map<string, FactStore>();

export function useFinancialData(ticker: string) {
  const [store, setStore] = useState<FactStore | null>(cache.get(ticker) ?? null);
  const [loading, setLoading] = useState(!cache.has(ticker));
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!ticker) {
      setStore(null);
      setLoading(false);
      return;
    }
    if (cache.has(ticker)) {
      setStore(cache.get(ticker)!);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);

    fetch(`/api/financials/${ticker}`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json() as Promise<ApiResponse>;
      })
      .then((data) => {
        if (cancelled) return;
        const fs = new FactStore(data.facts, data.company);
        cache.set(ticker, fs);
        setStore(fs);
        setLoading(false);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e.message);
        setLoading(false);
      });

    return () => { cancelled = true; };
  }, [ticker]);

  return { store, loading, error };
}
