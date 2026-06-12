"use client";

import { useMemo, useState } from "react";
import type { DimCell } from "./types";
import { fmtValue, comparePeriods } from "./constants";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

type Props = {
  dimensional: DimCell[];
};

type Frequency = "quarterly" | "annual";

const AXIS_LABEL: Record<string, string> = {
  product: "Product",
  geography: "Geography",
  customer_concentration: "Customer Concentration",
  business_segment: "Business Segment",
};

// Friendly labels for the Metric dropdown. Falls back to the raw uni_account.
const METRIC_LABEL: Record<string, string> = {
  revenue: "Revenue",
  operating_income: "Operating Income",
  operating_margin_pct: "Operating Margin %",
  revenue_pct_of_total: "% of Total Revenue",
  identifiable_assets: "Identifiable Assets",
  long_lived_assets: "Long-Lived Assets",
  ppe_net: "PP&E, net",
};

function filterByFrequency(rows: DimCell[], freq: Frequency): DimCell[] {
  return rows.filter((r) => {
    // Cumulative YTD facts (6M/9M) are never a canonical column — the
    // single-quarter and FY-annual facts are. Some NLM rows carry a 9M
    // cumulative tagged ytd_duration at a Qx period (e.g. Lumentum Q3_FY2025
    // Cloud & Networking = 986.7 9M alongside 365.2 single-quarter); without this
    // guard the pivot collapses both onto the Qx cell and may show the 9M total
    // in place of the quarter. Exclude ytd_duration from both views.
    if (r.period_kind === "ytd_duration") return false;
    const isQ = /^Q\d_FY\d{4}$/.test(r.period);
    const isFY = /^FY\d{4}$/.test(r.period);
    if (freq === "quarterly") return isQ;
    return isFY;
  });
}

function pivot(rows: DimCell[]): {
  members: string[];
  periods: string[];
  cells: Record<string, Record<string, DimCell>>;
} {
  const periodSet = new Set<string>();
  const memberMap = new Map<string, string>();
  for (const r of rows) {
    periodSet.add(r.period);
    if (!memberMap.has(r.member_key)) memberMap.set(r.member_key, r.member);
  }
  const periods = Array.from(periodSet).sort(comparePeriods);
  const members = Array.from(memberMap.keys()).sort((a, b) =>
    memberMap.get(a)!.localeCompare(memberMap.get(b)!),
  );
  const cells: Record<string, Record<string, DimCell>> = {};
  for (const k of members) cells[k] = {};
  for (const r of rows) {
    cells[r.member_key][r.period] = r;
  }
  return { members, periods, cells };
}

export function SegmentDashboard({ dimensional }: Props) {
  const [axis, setAxis] = useState<string>("product");
  const [uniAccount, setUniAccount] = useState<string>("revenue");
  const [frequency, setFrequency] = useState<Frequency>("annual");

  const axes = useMemo(
    () => Array.from(new Set(dimensional.map((d) => d.axis))).sort(),
    [dimensional],
  );
  const uniAccountsForAxis = useMemo(
    () =>
      Array.from(new Set(dimensional.filter((d) => d.axis === axis).map((d) => d.uni_account))).sort(),
    [dimensional, axis],
  );

  const safeUniAccount = uniAccountsForAxis.includes(uniAccount)
    ? uniAccount
    : uniAccountsForAxis[0];

  const subset = useMemo(
    () =>
      filterByFrequency(
        dimensional.filter((d) => d.axis === axis && d.uni_account === safeUniAccount),
        frequency,
      ),
    [dimensional, axis, safeUniAccount, frequency],
  );

  const { members, periods, cells } = useMemo(() => pivot(subset), [subset]);

  const colTotals: Record<string, number> = {};
  for (const p of periods) {
    colTotals[p] = members.reduce((sum, m) => sum + (cells[m][p]?.value ?? 0), 0);
  }

  // Members in an axis share one reporting unit; the Total row must format with
  // THAT unit, not a hardcoded scale — otherwise a USD_millions ticker (LITE/MU/
  // INTC) renders its total mis-scaled (e.g. 1,515 → "$1.5M" instead of "$1.5B").
  const axisUnit =
    members
      .map((m) => periods.map((p) => cells[m][p]?.unit).find(Boolean))
      .find(Boolean) ?? "USD_millions";

  if (axes.length === 0) {
    return <div className="p-4 text-sm text-muted-foreground">No dimensional facts available.</div>;
  }

  const showSharePct = safeUniAccount === "revenue";

  return (
    <div className="text-foreground">
      <div className="flex flex-wrap items-center gap-2 mb-3 text-sm">
        <label className="text-foreground">Axis:</label>
        <Select value={axis} onValueChange={setAxis}>
          <SelectTrigger className="w-[200px]" size="sm">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {axes.map((a) => (
              <SelectItem key={a} value={a}>
                {AXIS_LABEL[a] ?? a}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <label className="ml-2 text-foreground">Metric:</label>
        <Select value={safeUniAccount} onValueChange={setUniAccount}>
          <SelectTrigger className="w-[220px]" size="sm">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {uniAccountsForAxis.map((u) => (
              <SelectItem key={u} value={u}>
                {METRIC_LABEL[u] ?? u}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <div className="inline-flex rounded-md border border-border overflow-hidden ml-2">
          {(["annual", "quarterly"] as Frequency[]).map((f) => (
            <Button
              key={f}
              size="sm"
              variant={frequency === f ? "default" : "ghost"}
              onClick={() => setFrequency(f)}
              className="rounded-none border-r last:border-r-0 border-border"
            >
              {f}
            </Button>
          ))}
        </div>
      </div>

      {periods.length === 0 ? (
        <div className="text-sm text-muted-foreground">No data for current selection.</div>
      ) : (
        <div className="overflow-x-auto rounded border border-border bg-card">
          <table className="text-sm border-collapse w-full">
            <thead>
              <tr className="border-b border-border bg-muted">
                <th
                  className="text-left px-3 py-2 sticky left-0 z-10 font-semibold"
                  style={{ background: "var(--muted)" }}
                >
                  Member
                </th>
                {periods.map((p) => (
                  <th key={p} className="text-right px-3 py-2 whitespace-nowrap font-semibold">
                    {p}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {members.map((m) => (
                <tr
                  key={m}
                  className="border-b border-border bg-card"
                >
                  <td
                    className="px-3 py-1.5 sticky left-0 z-10"
                    style={{ background: "var(--card)" }}
                  >
                    {cells[m][periods[0]]?.member ?? m}
                  </td>
                  {periods.map((p) => {
                    const c = cells[m][p];
                    if (!c) {
                      return (
                        <td key={p} className="text-right px-3 py-1.5 text-muted-foreground/60">
                          —
                        </td>
                      );
                    }
                    return (
                      <td key={p} className="text-right px-3 py-1.5 whitespace-nowrap">
                        {fmtValue(c.value, c.unit)}
                        {showSharePct && c.unit === "USD_thousands" && colTotals[p] > 0 && (
                          <span className="ml-1 text-xs text-muted-foreground">
                            ({((c.value / colTotals[p]) * 100).toFixed(0)}%)
                          </span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
              {showSharePct && (
                <tr className="font-semibold bg-muted">
                  <td
                    className="px-3 py-1.5 sticky left-0 z-10"
                    style={{ background: "var(--muted)" }}
                  >
                    Total
                  </td>
                  {periods.map((p) => (
                    <td key={p} className="text-right px-3 py-1.5 whitespace-nowrap">
                      {fmtValue(colTotals[p], axisUnit)}
                    </td>
                  ))}
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
