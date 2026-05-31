"use client";

import { useMemo } from "react";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
  Legend,
  type ChartOptions,
  type TooltipItem,
} from "chart.js";
import { Line } from "react-chartjs-2";
import type { Matrix } from "./useFinancialMatrix";
import { CHART_COLORS, CHART_MAX_SELECTION, chartGroupOf, type UnitGroup } from "./constants";

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Legend);

type Props = {
  gaap: Matrix;
  nongaap?: Matrix;
  selectedKeys: string[];
  showNongaapColumn?: boolean;
  height?: number;
};

/**
 * Look up the (label, unit) of a uni_account inside the matrix. Returns
 * the row's display label from the matrix definition and the first
 * populated cell's unit (so format heuristics work even when the row's
 * latest period is "—").
 */
function describeRow(matrix: Matrix, key: string): { label: string; unit: string } {
  const row = matrix.rows.find((r) => r.key === key);
  const label = row?.label ?? key;
  let unit = "";
  for (const p of matrix.periods) {
    const c = matrix.cells[key]?.[p]?.cell;
    if (c) {
      unit = c.unit;
      break;
    }
  }
  return { label, unit };
}

function formatValue(value: number | null, unit: string, group: UnitGroup): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  // Always keep the sign in front of the currency symbol; default JS gives
  // ugly results like "$-0.70".
  const sign = value < 0 ? "-" : "";
  const abs = Math.abs(value);
  if (group === "pct") return `${value < 0 ? "-" : ""}${(abs * 100).toFixed(1)}%`;
  if (group === "multiple") return `${sign}${abs.toFixed(2)}x`;
  if (group === "per_share") return `${sign}$${abs.toFixed(2)}`;
  if (group === "shares") {
    if (unit === "thousands_shares") return `${sign}${(abs / 1000).toFixed(1)}M`;
    return `${sign}${abs.toFixed(1)}M`;
  }
  if (group === "monetary") {
    const absM = unit === "USD_thousands" ? abs / 1000 : abs;
    if (absM >= 1000) return `${sign}$${(absM / 1000).toFixed(2)}B`;
    return `${sign}$${absM.toFixed(1)}M`;
  }
  return String(value);
}

export function MatrixChart({
  gaap,
  nongaap,
  selectedKeys,
  showNongaapColumn = false,
  height = 280,
}: Props) {
  const periods = gaap.periods;

  // Resolve label + unit for each selected key, in selection order.
  const selectedRows = useMemo(
    () => selectedKeys.map((k) => ({ key: k, ...describeRow(gaap, k) })),
    [gaap, selectedKeys],
  );

  // Axis unit comes from the first selected row. The Viewer's row-toggle
  // handler enforces a single unit group across selections, so all rows
  // here share the same group in practice — but we still pick the first
  // defensively so a stray mismatch only mis-formats the tooltip, not the
  // entire axis.
  const axis = useMemo(() => {
    const first = selectedRows[0];
    if (!first) return { unit: "USD_thousands", group: "monetary" as UnitGroup };
    return { unit: first.unit, group: chartGroupOf(first.unit, first.key) };
  }, [selectedRows]);

  const datasets = useMemo(() => {
    const out: Array<{
      label: string;
      data: Array<number | null>;
      borderColor: string;
      backgroundColor: string;
      borderDash?: number[];
      tension: number;
      pointRadius: number;
      spanGaps: boolean;
    }> = [];
    selectedRows.forEach((row, i) => {
      const color = CHART_COLORS[i % CHART_COLORS.length];
      out.push({
        label: row.label,
        data: periods.map((p) => {
          const c = gaap.cells[row.key]?.[p]?.cell;
          return c ? c.value : null;
        }),
        borderColor: color,
        backgroundColor: color + "22",
        tension: 0.25,
        pointRadius: 3,
        spanGaps: true,
      });
      if (showNongaapColumn && nongaap) {
        const ngHasData = periods.some((p) => nongaap.cells[row.key]?.[p]?.cell);
        if (ngHasData) {
          out.push({
            label: `${row.label} (Non-GAAP)`,
            data: periods.map((p) => {
              const c = nongaap.cells[row.key]?.[p]?.cell;
              return c ? c.value : null;
            }),
            borderColor: color,
            backgroundColor: color + "11",
            borderDash: [4, 4],
            tension: 0.25,
            pointRadius: 2,
            spanGaps: true,
          });
        }
      }
    });
    return out;
  }, [gaap, nongaap, periods, selectedRows, showNongaapColumn]);

  const options: ChartOptions<"line"> = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: "index", intersect: false },
    plugins: {
      legend: {
        position: "bottom",
        labels: { boxWidth: 12, font: { size: 11 } },
      },
      tooltip: {
        callbacks: {
          label: (ctx: TooltipItem<"line">) =>
            `${ctx.dataset.label}: ${formatValue(ctx.parsed.y, axis.unit, axis.group)}`,
        },
      },
    },
    scales: {
      x: { ticks: { font: { size: 10 }, maxRotation: 45 } },
      y: {
        ticks: {
          font: { size: 10 },
          callback: (v) => formatValue(Number(v), axis.unit, axis.group),
        },
      },
    },
  };

  return (
    <div className="rounded border border-border bg-card p-3 mb-4">
      <div className="text-xs text-muted-foreground mb-2">
        Click rows in the table below to plot up to {CHART_MAX_SELECTION} metrics — selecting a
        fourth replaces the oldest.
      </div>
      <div style={{ height }}>
        {selectedKeys.length === 0 || periods.length === 0 ? (
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
            {periods.length === 0
              ? "No periods to plot."
              : "No metrics selected — click a row in the table."}
          </div>
        ) : (
          <Line data={{ labels: periods, datasets }} options={options} />
        )}
      </div>
    </div>
  );
}
