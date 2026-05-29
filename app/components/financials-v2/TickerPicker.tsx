"use client";

import { useRouter } from "next/navigation";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { KNOWN_TICKERS } from "./constants";

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
