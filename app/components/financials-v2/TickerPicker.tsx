"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { groupTickersByMarket } from "./tickerGroups";
import type { CompanyListItem, TickerGroup } from "./tickerGroups";

type Props = {
  current: string;
};

export function TickerPicker({ current }: Props) {
  const router = useRouter();
  // Start from the fallback (null → US-only KNOWN_TICKERS) so the picker renders
  // immediately and never breaks if discovery is slow or fails. Replaced by the
  // discovered, market-grouped list once /api/financials/companies resolves.
  const [groups, setGroups] = useState<TickerGroup[]>(() => groupTickersByMarket(null));

  useEffect(() => {
    let cancelled = false;
    fetch("/api/financials/companies")
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(`HTTP ${res.status}`))))
      .then((body: { companies?: CompanyListItem[] }) => {
        if (cancelled) return;
        setGroups(groupTickersByMarket(body.companies ?? null));
      })
      .catch(() => {
        // Keep the fallback groups already in state — US never breaks.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <Select
      value={current}
      onValueChange={(t) => router.push(`/financials/${t}`)}
    >
      <SelectTrigger className="w-[140px]" aria-label="Switch ticker">
        <SelectValue placeholder="Select ticker" />
      </SelectTrigger>
      <SelectContent>
        {groups.map((g) => (
          <SelectGroup key={g.market}>
            <SelectLabel>{g.label}</SelectLabel>
            {g.tickers.map((t) => (
              <SelectItem key={t.ticker} value={t.ticker}>
                {t.ticker}
              </SelectItem>
            ))}
          </SelectGroup>
        ))}
      </SelectContent>
    </Select>
  );
}
