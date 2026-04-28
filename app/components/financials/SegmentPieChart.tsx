"use client";

import { useState } from "react";
import {
  Chart as ChartJS,
  ArcElement,
  Tooltip,
  Legend,
} from "chart.js";
import { Doughnut } from "react-chartjs-2";
import { CHART_COLORS } from "./constants";

ChartJS.register(ArcElement, Tooltip, Legend);

interface SegmentPieChartProps {
  /** segment name → period → value */
  segVals: Record<string, Record<string, number | null>>;
  periods: string[];
  formatValue: (value: number) => string;
}

export default function SegmentPieChart({ segVals, periods, formatValue }: SegmentPieChartProps) {
  const [selectedPeriod, setSelectedPeriod] = useState(periods[periods.length - 1] || "");

  if (!periods.length) return null;

  const segNames = Object.keys(segVals);
  const values = segNames.map((s) => segVals[s]?.[selectedPeriod] ?? 0);
  const total = values.reduce((a, b) => a + b, 0);

  return (
    <div className="mb-4 rounded-md bg-[var(--bg-card)] p-4 shadow-sm">
      {/* Period selector */}
      <div className="mb-3 flex flex-wrap items-center gap-1">
        <span className="mr-1 text-[11px] font-medium text-[var(--text-muted)]">Period:</span>
        {periods.map((p) => (
          <button
            key={p}
            onClick={() => setSelectedPeriod(p)}
            className={`rounded border px-2 py-0.5 text-[11px] font-semibold transition-all select-none ${
              selectedPeriod === p
                ? "border-[var(--text)] bg-[var(--text)] text-[var(--bg-card)]"
                : "border-[var(--border)] bg-[var(--bg-subtle)] text-[var(--text-muted)] hover:border-[var(--text-muted)]"
            }`}
          >
            {p}
          </button>
        ))}
      </div>

      <div className="relative mx-auto h-[240px] w-[240px]">
        <Doughnut
          data={{
            labels: segNames,
            datasets: [
              {
                data: values,
                backgroundColor: segNames.map((_, i) => CHART_COLORS[i % CHART_COLORS.length]),
                borderColor: "var(--bg-card)",
                borderWidth: 2,
              },
            ],
          }}
          options={{
            responsive: true,
            maintainAspectRatio: false,
            cutout: "55%",
            plugins: {
              tooltip: {
                callbacks: {
                  label: (ctx) => {
                    const v = ctx.parsed;
                    const pct = total > 0 ? ((v / total) * 100).toFixed(1) : "0.0";
                    return `${ctx.label}: ${formatValue(v)} (${pct}%)`;
                  },
                },
              },
              legend: {
                position: "bottom" as const,
                labels: { boxWidth: 12, font: { size: 11 }, padding: 12 },
              },
            },
          }}
        />
      </div>
    </div>
  );
}
