"use client";

import { useRouter } from "next/navigation";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

// Pre-onboarded tickers. Expand as we ingest more SEC filings.
// Should match docs/STATUS.md ticker registry.
export const KNOWN_TICKERS = ["AAOI", "INTC", "LITE", "SNDK"] as const;

type Props = {
  current: string;
};

export function TickerPicker({ current }: Props) {
  const router = useRouter();
  return (
    <Select
      value={current}
      onValueChange={(t) => router.push(`/financials/${t}`)}
    >
      <SelectTrigger className="w-[140px]" aria-label="Switch ticker">
        <SelectValue placeholder="Select ticker" />
      </SelectTrigger>
      <SelectContent>
        {KNOWN_TICKERS.map((t) => (
          <SelectItem key={t} value={t}>
            {t}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
