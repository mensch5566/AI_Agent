"use client";

import { useState, useMemo, useEffect } from "react";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
  Legend,
} from "chart.js";
import { Line } from "react-chartjs-2";
import {
  TOTAL_KEYS, sortPeriods, fmtVal, labelFor, isPct, CHART_COLORS,
  type ValMap, type FinData,
  type GrowthMode, prevQoQ, prevYoY, growthPct, fmtGrowth, skipGrowthForKey,
  getIncompleteFYs,
} from "./constants";
import { useFinancialData, toAnnualData } from "./useFinancialData";

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Legend);

/* ================================================================
   Row types
   ================================================================ */
type TableRow =
  | { type: "section"; label: string }
  | { type: "data"; key: string; label: string; vals: ValMap };

/* ================================================================
   Row builders for each statement type
   ================================================================ */

function buildIncomeRows(data: FinData): TableRow[] {
  const src = data.income_statement || {};
  return Object.entries(src).map(([key, vals]) => ({
    type: "data" as const,
    key,
    label: labelFor(key),
    vals: vals as ValMap,
  }));
}

function buildBalanceSheetRows(data: FinData): TableRow[] {
  const BS = data.balance_sheet || {};
  const rows: TableRow[] = [];
  for (const [secKey, secLabel] of [
    ["assets", "ASSETS"],
    ["liabilities", "LIABILITIES"],
    ["equity", "EQUITY"],
  ] as const) {
    const sec = BS[secKey];
    if (!sec) continue;
    rows.push({ type: "section", label: secLabel });
    for (const key of Object.keys(sec)) {
      rows.push({ type: "data", key, label: labelFor(key), vals: sec[key] });
    }
  }
  return rows;
}

function buildCashFlowRows(data: FinData): TableRow[] {
  const CF = data.cash_flow_statement || {};
  const rows: TableRow[] = [];
  for (const [secKey, secLabel] of [
    ["operating_activities", "OPERATING ACTIVITIES"],
    ["investing_activities", "INVESTING ACTIVITIES"],
    ["financing_activities", "FINANCING ACTIVITIES"],
  ] as const) {
    const sec = CF[secKey];
    if (!sec) continue;
    rows.push({ type: "section", label: secLabel });
    for (const [key, vals] of Object.entries(sec)) {
      if (typeof vals === "object" && vals !== null && !Array.isArray(vals))
        rows.push({ type: "data", key, label: labelFor(key), vals: vals as ValMap });
    }
  }
  rows.push({ type: "section", label: "SUMMARY" });
  for (const key of ["fx_effect_on_cash", "net_change_in_cash", "beginning_cash", "ending_cash", "free_cash_flow"]) {
    if (CF[key] && typeof CF[key] === "object")
      rows.push({ type: "data", key, label: labelFor(key), vals: CF[key] });
  }
  return rows;
}

const ROW_BUILDERS: Record<string, (data: FinData) => TableRow[]> = {
  income_statement: buildIncomeRows,
  balance_sheet: buildBalanceSheetRows,
  cash_flow_statement: buildCashFlowRows,
};

function getPeriodsKey(statement: string) {
  return statement === "balance_sheet"
    ? "periods_balance_sheet"
    : "periods_income_statement";
}

/* ================================================================
   Growth Toggle Component
   ================================================================ */
function GrowthToggle({ mode, setMode, isAnnual }: { mode: GrowthMode; setMode: (m: GrowthMode) => void; isAnnual: boolean }) {
  const options: { key: GrowthMode; label: string; disabled: boolean }[] = [
    { key: "value", label: "Value", disabled: false },
    { key: "qoq", label: "QoQ %", disabled: isAnnual },
    { key: "yoy", label: "YoY %", disabled: false },
  ];
  return (
    <div className="flex gap-1">
      {options.map(({ key, label, disabled }) => (
        <button
          key={key}
          onClick={() => !disabled && setMode(key)}
          disabled={disabled}
          className={`rounded border px-2.5 py-1 text-[11px] font-semibold transition-all select-none ${
            disabled
              ? "cursor-not-allowed border-[var(--border)] bg-[var(--bg-subtle)] text-[var(--text-faint)] opacity-40"
              : mode === key
                ? "border-[var(--text)] bg-[var(--text)] text-[var(--bg-card)]"
                : "border-[var(--border)] bg-[var(--bg-subtle)] text-[var(--text-muted)] hover:border-[var(--text-muted)]"
          }`}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

/* ================================================================
   FinancialTable Component
   ================================================================ */

interface FinancialTableProps {
  ticker: string;
  statement: "income_statement" | "balance_sheet" | "cash_flow_statement";
  metrics?: string[];
  maxPeriods?: number;
  defaultView?: "quarterly" | "annual";
}

export default function FinancialTable({
  ticker,
  statement,
  metrics,
  maxPeriods,
  defaultView = "quarterly",
}: FinancialTableProps) {
  const { data: rawData, loading, error } = useFinancialData(ticker);
  const [viewMode, setViewMode] = useState<"quarterly" | "annual">(defaultView);
  const [growthMode, setGrowthMode] = useState<GrowthMode>("value");

  // Reset QoQ to Value when switching to Annual
  useEffect(() => { if (viewMode === "annual" && growthMode === "qoq") setGrowthMode("value"); }, [viewMode]);

  const displayData = useMemo(() => {
    if (!rawData) return null;
    return viewMode === "annual" ? toAnnualData(rawData) : rawData;
  }, [rawData, viewMode]);

  // Detect incomplete FYs in annual mode (must be before early returns)
  const incompleteFYs = useMemo(() => {
    if (viewMode !== "annual" || !rawData) return new Map<string, number>();
    const qPeriods = rawData.metadata[getPeriodsKey(statement)] || [];
    return getIncompleteFYs(qPeriods);
  }, [viewMode, rawData, statement]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-10 text-sm text-[var(--text-faint)]">
        載入財務數據中...
      </div>
    );
  }

  if (error || !displayData) {
    return (
      <div className="py-6 text-center text-sm text-[var(--text-faint)]">
        {error ? `無法載入 ${ticker} 財務數據：${error}` : "無數據"}
      </div>
    );
  }

  // Build rows
  const builder = ROW_BUILDERS[statement];
  if (!builder) return null;
  let allRows = builder(displayData);

  // Filter to specific metrics if provided
  if (metrics && metrics.length > 0) {
    const metricSet = new Set(metrics);
    allRows = allRows.filter((row) => {
      if (row.type === "section") return true;
      return metricSet.has(row.key);
    });
    // Remove orphan section headers
    const cleaned: TableRow[] = [];
    for (let i = 0; i < allRows.length; i++) {
      if (allRows[i].type === "section") {
        let hasData = false;
        for (let j = i + 1; j < allRows.length; j++) {
          if (allRows[j].type === "section") break;
          if (allRows[j].type === "data") { hasData = true; break; }
        }
        if (hasData) cleaned.push(allRows[i]);
      } else {
        cleaned.push(allRows[i]);
      }
    }
    allRows = cleaned;
  }

  // Get periods and apply maxPeriods limit
  const periodsKey = getPeriodsKey(statement);
  let periods = sortPeriods(displayData.metadata[periodsKey] || []);
  if (maxPeriods && maxPeriods > 0 && periods.length > maxPeriods) {
    periods = periods.slice(-maxPeriods);
  }

  if (!allRows.length) {
    return <div className="py-6 text-center text-sm text-[var(--text-faint)]">無數據</div>;
  }

  const isGrowth = growthMode !== "value";
  const prevFn = growthMode === "qoq" ? prevQoQ : prevYoY;
  const hasIncomplete = viewMode === "annual" && incompleteFYs.size > 0;

  return (
    <div>
      {/* Controls: view toggle + growth toggle */}
      <div className="mb-3 flex items-center justify-between">
        <GrowthToggle mode={growthMode} setMode={setGrowthMode} isAnnual={viewMode === "annual"} />
        <div className="flex gap-1">
          {(["quarterly", "annual"] as const).map((m) => (
            <button
              key={m}
              onClick={() => setViewMode(m)}
              className={`rounded border px-2.5 py-1 text-xs font-semibold transition-all select-none ${
                viewMode === m
                  ? "border-[var(--primary)] bg-[var(--primary)] text-white"
                  : "border-[var(--border)] bg-[var(--bg-subtle)] text-[var(--text-muted)] hover:border-[var(--primary)]"
              }`}
            >
              {m === "quarterly" ? "季度" : "年度"}
            </button>
          ))}
        </div>
      </div>

      {/* Chart (income statement only) */}
      {statement === "income_statement" && (() => {
        const chartMetrics = [
          { key: "revenue", label: "Revenue" },
          { key: "gross_profit", label: "Gross Profit" },
          { key: "operating_income", label: "Operating Income" },
          { key: "net_income", label: "Net Income" },
        ].filter(({ key }) => !metrics || metrics.includes(key));
        const is = displayData[statement] || {};
        if (!chartMetrics.length) return null;
        return (
          <div className="mb-4 rounded-md bg-[var(--bg-card)] p-4 shadow-sm">
            <div className="relative h-[260px]">
              <Line
                data={{
                  labels: periods,
                  datasets: chartMetrics
                    .filter(({ key }) => is[key])
                    .map(({ key, label }, i) => ({
                      label,
                      data: isGrowth
                        ? periods.map((p) => { const pk = prevFn(p); const g = growthPct(is[key]?.[p], pk ? is[key]?.[pk] : null); return g != null ? +(g * 100).toFixed(1) : null; })
                        : periods.map((p) => is[key]?.[p] ?? null),
                      borderColor: CHART_COLORS[i % CHART_COLORS.length],
                      backgroundColor: CHART_COLORS[i % CHART_COLORS.length] + "cc",
                      tension: 0.3,
                      pointRadius: 3,
                    })),
                }}
                options={{
                  responsive: true,
                  maintainAspectRatio: false,
                  interaction: { mode: "index" as const, intersect: false },
                  plugins: {
                    tooltip: { callbacks: { label: (ctx) => isGrowth ? `${ctx.dataset.label}: ${ctx.parsed.y?.toFixed(1)}%` : `${ctx.dataset.label}: $${ctx.parsed.y?.toLocaleString()}M` } },
                    legend: { position: "bottom" as const, labels: { boxWidth: 12, font: { size: 11 } } },
                  },
                  scales: {
                    x: { ticks: { font: { size: 10 }, maxRotation: 45 } },
                    y: { ticks: { font: { size: 10 }, callback: (v) => isGrowth ? `${v}%` : `$${v}M` } },
                  },
                }}
              />
            </div>
          </div>
        );
      })()}

      {/* Table */}
      <div className="overflow-x-auto rounded-md shadow-sm">
        <table className="w-full border-collapse bg-[var(--bg-card)] text-xs">
          <thead>
            <tr>
              <th className="sticky left-0 z-[11] min-w-[180px] border border-[var(--border)] bg-[#1f4e79] px-3 py-1.5 text-left font-semibold text-white">
                Metric
              </th>
              {periods.map((p) => {
                const end = displayData.filings?.[p]?.period_end ?? "";
                const qCount = incompleteFYs.get(p);
                return (
                  <th key={p} className="border border-[var(--border)] bg-[#1f4e79] px-3 py-1.5 text-center font-semibold text-white whitespace-nowrap">
                    {p}
                    {qCount && <span className="ml-1 inline-block rounded bg-amber-500/80 px-1 py-px text-[9px] font-normal leading-tight text-white" title={`僅 ${qCount} 季數據`}>{qCount}Q</span>}
                    {end && <span className="block text-[10px] font-normal text-white/70">{end}</span>}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {allRows.map((row, i) => {
              if (row.type === "section") {
                return (
                  <tr key={`sec-${i}`}>
                    <td
                      colSpan={periods.length + 1}
                      className="border border-[var(--border)] bg-[#d6e4f0] px-3 py-1.5 text-[11px] font-bold uppercase tracking-wide text-[#1f4e79]"
                    >
                      {row.label}
                    </td>
                  </tr>
                );
              }
              const isTotal = TOTAL_KEYS.has(row.key);
              const bgBase = isTotal
                ? "bg-[var(--bg-highlight)]"
                : i % 2 === 0
                  ? "bg-[var(--bg-subtle)]"
                  : "bg-[var(--bg-card)]";
              const textCls = isTotal ? "font-bold text-[#7b3f00]" : "";
              const showGrowth = isGrowth && !skipGrowthForKey(row.key);
              return (
                <tr key={row.key + i}>
                  <td className={`sticky left-0 z-[5] border border-[var(--border)] px-3 py-1.5 text-left font-medium whitespace-nowrap ${bgBase} ${textCls}`}>
                    {row.label}
                  </td>
                  {periods.map((p) => {
                    if (showGrowth) {
                      const curr = row.vals?.[p];
                      const pk = prevFn(p);
                      const prev = pk ? row.vals?.[pk] : null;
                      const g = growthPct(curr, prev);
                      const f = fmtGrowth(g);
                      const isPartial = incompleteFYs.has(p) || (pk ? incompleteFYs.has(pk) : false);
                      return (
                        <td
                          key={p}
                          title={isPartial ? "數據未完整，僅部分季度" : undefined}
                          className={`border border-[var(--border)] px-3 py-1.5 tabular-nums ${bgBase} ${
                            f.cls === "negative" ? "text-right text-[#c0392b]"
                              : f.cls === "positive" ? "text-right text-[#27ae60]"
                              : f.cls === "null-val" ? "text-center text-[#7f8c8d]"
                              : "text-right"
                          }`}
                        >
                          {f.text}{isPartial && f.cls !== "null-val" && <span className="ml-0.5 text-[9px] text-amber-500">*</span>}
                        </td>
                      );
                    }
                    const v = row.vals?.[p];
                    const f = fmtVal(v, row.key, rawData?.metadata?.currency);
                    return (
                      <td
                        key={p}
                        className={`border border-[var(--border)] px-3 py-1.5 tabular-nums ${bgBase} ${textCls} ${
                          f.cls === "negative"
                            ? "text-right text-[#c0392b]"
                            : f.cls === "null-val"
                              ? "text-center text-[#7f8c8d]"
                              : "text-right"
                        }`}
                      >
                        {f.text}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="mt-1.5 flex justify-between text-[10px]">
        {hasIncomplete && <span className="text-amber-600">* 數據未完整（僅部分季度），YoY 比較可能失真</span>}
        <span className="ml-auto text-[var(--text-faint)]">Unit: $M（EPS 除外）</span>
      </div>
    </div>
  );
}
