"use client";

/* eslint-disable @typescript-eslint/no-explicit-any */
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
  TOTAL_KEYS, fmtVal, labelFor, CHART_COLORS,
  type GrowthMode, prevQoQ, prevYoY, growthPct, fmtGrowth, skipGrowthForKey,
} from "./constants";
import { useFinancialData } from "./useFinancialData";
import { FactStore, type ValMap } from "./FactStore";

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Legend);

type TableRow =
  | { type: "section"; label: string }
  | { type: "data"; key: string; label: string; vals: ValMap };

function buildRows(store: FactStore, statement: string): TableRow[] {
  if (statement === "income_statement") {
    return store.metrics("income_statement").map((key) => ({
      type: "data" as const, key, label: labelFor(key),
      vals: store.valMap("income_statement", key),
    }));
  }
  if (statement === "balance_sheet") {
    const rows: TableRow[] = [];
    for (const [stmt, label] of [
      ["balance_sheet_assets", "ASSETS"],
      ["balance_sheet_liabilities", "LIABILITIES"],
      ["balance_sheet_equity", "EQUITY"],
    ] as const) {
      const metrics = store.metrics(stmt);
      if (!metrics.length) continue;
      rows.push({ type: "section", label });
      for (const key of metrics) rows.push({ type: "data", key, label: labelFor(key), vals: store.valMap(stmt, key) });
    }
    return rows;
  }
  if (statement === "cash_flow_statement") {
    const rows: TableRow[] = [];
    for (const [stmt, label] of [
      ["cash_flow_operating", "OPERATING ACTIVITIES"],
      ["cash_flow_investing", "INVESTING ACTIVITIES"],
      ["cash_flow_financing", "FINANCING ACTIVITIES"],
    ] as const) {
      const metrics = store.metrics(stmt);
      if (!metrics.length) continue;
      rows.push({ type: "section", label });
      for (const key of metrics) rows.push({ type: "data", key, label: labelFor(key), vals: store.valMap(stmt, key) });
    }
    const summary = store.metrics("cash_flow_summary");
    if (summary.length) {
      rows.push({ type: "section", label: "SUMMARY" });
      for (const key of summary) rows.push({ type: "data", key, label: labelFor(key), vals: store.valMap("cash_flow_summary", key) });
    }
    return rows;
  }
  return [];
}

function getPeriods(store: FactStore, statement: string): string[] {
  if (statement === "balance_sheet") return store.periodsBS();
  return store.periodsIS();
}

function GrowthToggle({ mode, setMode, isAnnual }: { mode: GrowthMode; setMode: (m: GrowthMode) => void; isAnnual: boolean }) {
  const options: { key: GrowthMode; label: string; disabled: boolean }[] = [
    { key: "value", label: "Value", disabled: false },
    { key: "qoq", label: "QoQ %", disabled: isAnnual },
    { key: "yoy", label: "YoY %", disabled: false },
  ];
  return (
    <div className="flex gap-1">
      {options.map(({ key, label, disabled }) => (
        <button key={key} onClick={() => !disabled && setMode(key)} disabled={disabled}
          className={`rounded border px-2.5 py-1 text-[11px] font-semibold transition-all select-none ${
            disabled ? "cursor-not-allowed border-[var(--border)] bg-[var(--bg-subtle)] text-[var(--text-faint)] opacity-40"
              : mode === key ? "border-[var(--text)] bg-[var(--text)] text-[var(--bg-card)]"
              : "border-[var(--border)] bg-[var(--bg-subtle)] text-[var(--text-muted)] hover:border-[var(--text-muted)]"
          }`}
        >{label}</button>
      ))}
    </div>
  );
}

interface FinancialTableProps {
  ticker: string;
  statement: "income_statement" | "balance_sheet" | "cash_flow_statement";
  metrics?: string[];
  maxPeriods?: number;
  defaultView?: "quarterly" | "annual";
}

export default function FinancialTable({
  ticker, statement, metrics, maxPeriods, defaultView = "quarterly",
}: FinancialTableProps) {
  const { store: rawStore, loading, error } = useFinancialData(ticker);
  const [viewMode, setViewMode] = useState<"quarterly" | "annual">(defaultView);
  const [growthMode, setGrowthMode] = useState<GrowthMode>("value");

  useEffect(() => { if (viewMode === "annual" && growthMode === "qoq") setGrowthMode("value"); }, [viewMode]);

  const store = useMemo(() => {
    if (!rawStore) return null;
    return viewMode === "annual" ? rawStore.toAnnual() : rawStore;
  }, [rawStore, viewMode]);

  if (loading) return <div className="flex items-center justify-center py-10 text-sm text-[var(--text-faint)]">載入財務數據中...</div>;
  if (error || !store) return <div className="py-6 text-center text-sm text-[var(--text-faint)]">{error ? `無法載入 ${ticker} 財務數據：${error}` : "無數據"}</div>;

  let allRows = buildRows(store, statement);

  if (metrics?.length) {
    const metricSet = new Set(metrics);
    allRows = allRows.filter((row) => row.type === "section" || metricSet.has(row.key));
    const cleaned: TableRow[] = [];
    for (let i = 0; i < allRows.length; i++) {
      if (allRows[i].type === "section") {
        let hasData = false;
        for (let j = i + 1; j < allRows.length; j++) {
          if (allRows[j].type === "section") break;
          if (allRows[j].type === "data") { hasData = true; break; }
        }
        if (hasData) cleaned.push(allRows[i]);
      } else cleaned.push(allRows[i]);
    }
    allRows = cleaned;
  }

  let periods = getPeriods(store, statement);
  if (maxPeriods && maxPeriods > 0 && periods.length > maxPeriods) periods = periods.slice(-maxPeriods);
  if (!allRows.length) return <div className="py-6 text-center text-sm text-[var(--text-faint)]">無數據</div>;

  const isGrowth = growthMode !== "value";
  const prevFn = growthMode === "qoq" ? prevQoQ : prevYoY;

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <GrowthToggle mode={growthMode} setMode={setGrowthMode} isAnnual={viewMode === "annual"} />
        <div className="flex gap-1">
          {(["quarterly", "annual"] as const).map((m) => (
            <button key={m} onClick={() => setViewMode(m)}
              className={`rounded border px-2.5 py-1 text-xs font-semibold transition-all select-none ${
                viewMode === m ? "border-[var(--primary)] bg-[var(--primary)] text-white" : "border-[var(--border)] bg-[var(--bg-subtle)] text-[var(--text-muted)] hover:border-[var(--primary)]"
              }`}
            >{m === "quarterly" ? "季度" : "年度"}</button>
          ))}
        </div>
      </div>

      {statement === "income_statement" && (() => {
        const chartMetrics = [
          { key: "revenue", label: "Revenue" },
          { key: "gross_profit", label: "Gross Profit" },
          { key: "operating_income", label: "Operating Income" },
          { key: "net_income", label: "Net Income" },
        ].filter(({ key }) => !metrics || metrics.includes(key));
        if (!chartMetrics.length) return null;
        return (
          <div className="mb-4 rounded-md bg-[var(--bg-card)] p-4 shadow-sm">
            <div className="relative h-[260px]">
              <Line data={{
                labels: periods,
                datasets: chartMetrics
                  .filter(({ key }) => store.metrics("income_statement").includes(key))
                  .map(({ key, label }, i) => {
                    const vals = store.valMap("income_statement", key);
                    return {
                      label, data: isGrowth
                        ? periods.map((p) => { const pk = prevFn(p); const g = growthPct(vals[p], pk ? vals[pk] : null); return g != null ? +(g * 100).toFixed(1) : null; })
                        : periods.map((p) => vals[p] ?? null),
                      borderColor: CHART_COLORS[i % CHART_COLORS.length],
                      backgroundColor: CHART_COLORS[i % CHART_COLORS.length] + "cc",
                      tension: 0.3, pointRadius: 3,
                    };
                  }),
              }} options={{
                responsive: true, maintainAspectRatio: false,
                interaction: { mode: "index" as const, intersect: false },
                plugins: {
                  tooltip: { callbacks: { label: (ctx) => isGrowth ? `${ctx.dataset.label}: ${ctx.parsed.y?.toFixed(1)}%` : `${ctx.dataset.label}: $${ctx.parsed.y?.toLocaleString()}M` } },
                  legend: { position: "bottom" as const, labels: { boxWidth: 12, font: { size: 11 } } },
                },
                scales: {
                  x: { ticks: { font: { size: 10 }, maxRotation: 45 } },
                  y: { ticks: { font: { size: 10 }, callback: (v) => isGrowth ? `${v}%` : `$${v}M` } },
                },
              }} />
            </div>
          </div>
        );
      })()}

      <div className="overflow-x-auto rounded-md shadow-sm">
        <table className="w-full border-collapse bg-[var(--bg-card)] text-xs">
          <thead>
            <tr>
              <th className="sticky left-0 z-[11] min-w-[180px] border border-[var(--border)] bg-[#1f4e79] px-3 py-1.5 text-left font-semibold text-white">Metric</th>
              {periods.map((p) => {
                const end = store.periodEnd(p);
                const qCount = store.incompleteFYQuarters(p);
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
                return <tr key={`sec-${i}`}><td colSpan={periods.length + 1} className="border border-[var(--border)] bg-[#d6e4f0] px-3 py-1.5 text-[11px] font-bold uppercase tracking-wide text-[#1f4e79]">{row.label}</td></tr>;
              }
              const isTotal = TOTAL_KEYS.has(row.key);
              const bgBase = isTotal ? "bg-[var(--bg-highlight)]" : i % 2 === 0 ? "bg-[var(--bg-subtle)]" : "bg-[var(--bg-card)]";
              const textCls = isTotal ? "font-bold text-[#7b3f00]" : "";
              const showGrowth = isGrowth && !skipGrowthForKey(row.key);
              return (
                <tr key={row.key + i}>
                  <td className={`sticky left-0 z-[5] border border-[var(--border)] px-3 py-1.5 text-left font-medium whitespace-nowrap ${bgBase} ${textCls}`}>{row.label}</td>
                  {periods.map((p) => {
                    if (showGrowth) {
                      const curr = row.vals?.[p]; const pk = prevFn(p); const prev = pk ? row.vals?.[pk] : null;
                      const g = growthPct(curr, prev); const f = fmtGrowth(g);
                      const isPartial = !!(store.incompleteFYQuarters(p) || (pk && store.incompleteFYQuarters(pk)));
                      return (
                        <td key={p} title={isPartial ? "數據未完整，僅部分季度" : undefined}
                          className={`border border-[var(--border)] px-3 py-1.5 tabular-nums ${bgBase} ${
                            f.cls === "negative" ? "text-right text-[#c0392b]" : f.cls === "positive" ? "text-right text-[#27ae60]" : f.cls === "null-val" ? "text-center text-[#7f8c8d]" : "text-right"
                          }`}>
                          {f.text}{isPartial && f.cls !== "null-val" && <span className="ml-0.5 text-[9px] text-amber-500">*</span>}
                        </td>
                      );
                    }
                    const v = row.vals?.[p]; const f = fmtVal(v, row.key, store.currency);
                    return (
                      <td key={p} className={`border border-[var(--border)] px-3 py-1.5 tabular-nums ${bgBase} ${textCls} ${
                        f.cls === "negative" ? "text-right text-[#c0392b]" : f.cls === "null-val" ? "text-center text-[#7f8c8d]" : "text-right"
                      }`}>{f.text}</td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="mt-1.5 text-right text-[10px] text-[var(--text-faint)]">Unit: $M（EPS 除外）</div>
    </div>
  );
}
