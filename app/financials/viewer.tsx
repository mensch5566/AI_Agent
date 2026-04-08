"use client";

/* eslint-disable @typescript-eslint/no-explicit-any */
import { useState, useEffect, useMemo } from "react";
import Link from "next/link";
import ThemeToggle from "@/app/components/ThemeToggle";
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
import SegmentPieChart from "@/app/components/financials/SegmentPieChart";
import {
  TICKER_LABELS, TOTAL_KEYS, RATIO_ORDER, RATIO_DEFINITIONS, CHART_COLORS,
  sortPeriods, isPct, isEps, fmtVal, labelFor, sortMetrics,
  IS_METRIC_ORDER, BS_ASSETS_ORDER, BS_LIABILITIES_ORDER, BS_EQUITY_ORDER,
  CF_OPERATING_ORDER, CF_INVESTING_ORDER, CF_FINANCING_ORDER, CF_SUMMARY_ORDER,
  prevQoQ, prevYoY, growthPct, fmtGrowth, skipGrowthForKey,
  type GrowthMode,
} from "@/app/components/financials/constants";
import { useFinancialData } from "@/app/components/financials/useFinancialData";
import { FactStore, type ValMap } from "@/app/components/financials/FactStore";

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Legend);

/* ================================================================
   Shared components
   ================================================================ */

function GrowthToggle({ mode, setMode, showQoQ = true }: { mode: GrowthMode; setMode: (m: GrowthMode) => void; showQoQ?: boolean }) {
  const options: [GrowthMode, string][] = showQoQ
    ? [["value", "Value"], ["qoq", "QoQ %"], ["yoy", "YoY %"]]
    : [["value", "Value"], ["yoy", "YoY %"]];
  return (
    <div className="flex gap-1">
      {options.map(([key, label]) => (
        <button
          key={key}
          onClick={() => setMode(key)}
          className={`rounded border px-2.5 py-1 text-[11px] font-semibold transition-all select-none ${
            mode === key
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

/* ── Row types for table rendering ── */
type TableRow =
  | { type: "section"; label: string }
  | { type: "data"; key: string; label: string; vals: ValMap };

/* ── Generic data table ── */
function DataTable({
  periods,
  rows,
  store,
  growthMode = "value",
}: {
  periods: string[];
  rows: TableRow[];
  store: FactStore;
  growthMode?: GrowthMode;
}) {
  if (!rows.length) return <div className="p-10 text-center text-sm text-[#7f8c8d]">No data available.</div>;

  const isGrowth = growthMode !== "value";
  const prevFn = growthMode === "qoq" ? prevQoQ : prevYoY;

  return (
    <div className="overflow-x-auto rounded-md shadow-sm">
      <table className="w-full border-collapse bg-[var(--bg-card)] text-xs">
        <thead>
          <tr>
            <th className="sticky left-0 z-[11] min-w-[260px] border border-[var(--border)] bg-[#1f4e79] px-3 py-1.5 text-left font-semibold text-white">
              Metric
            </th>
            {periods.map((p) => {
              const end = store.periodEnd(p);
              const qCount = store.incompleteFYQuarters(p);
              return (
                <th key={p} className="border border-[var(--border)] bg-[#1f4e79] px-3 py-1.5 text-center font-semibold text-white">
                  {p}
                  {qCount && <span className="ml-1 inline-block rounded bg-amber-500/80 px-1 py-px text-[9px] font-normal leading-tight text-white" title={`僅 ${qCount} 季數據`}>{qCount}Q</span>}
                  {end && <span className="block text-[10px] font-normal text-white/70">{end}</span>}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => {
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
            const bgBase = isTotal ? "bg-[var(--bg-highlight)]" : i % 2 === 0 ? "bg-[var(--bg-subtle)]" : "bg-[var(--bg-card)]";
            const textCls = isTotal ? "font-bold text-[#7b3f00]" : "";
            const skipGrowth = isGrowth && skipGrowthForKey(row.key);
            return (
              <tr key={row.key + i}>
                <td className={`sticky left-0 z-[5] border border-[var(--border)] px-3 py-1.5 text-left font-medium ${bgBase} ${textCls}`}>
                  {row.label}
                </td>
                {periods.map((p) => {
                  if (isGrowth && !skipGrowth) {
                    const curr = row.vals?.[p];
                    const prevKey = prevFn(p);
                    const prev = prevKey ? row.vals?.[prevKey] : null;
                    const g = growthPct(curr, prev);
                    const f = fmtGrowth(g);
                    const qc = store.incompleteFYQuarters(p);
                    const pqc = prevKey ? store.incompleteFYQuarters(prevKey) : null;
                    const isPartial = !!(qc || pqc);
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
                  const f = fmtVal(v, row.key, store.currency);
                  return (
                    <td
                      key={p}
                      className={`border border-[var(--border)] px-3 py-1.5 tabular-nums ${bgBase} ${textCls} ${
                        f.cls === "negative" ? "text-right text-[#c0392b]" : f.cls === "null-val" ? "text-center text-[#7f8c8d]" : "text-right"
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
  );
}

/* ================================================================
   Income Statement
   ================================================================ */
const IS_CHART_METRICS = [
  { key: "revenue", label: "Revenue" },
  { key: "gross_profit", label: "Gross Profit" },
  { key: "operating_income", label: "Operating Income" },
  { key: "net_income", label: "Net Income" },
];

function IncomeStatement({ store, viewMode }: { store: FactStore; viewMode: "quarterly" | "annual" }) {
  const [growthMode, setGrowthMode] = useState<GrowthMode>("value");
  useEffect(() => { if (viewMode === "annual" && growthMode === "qoq") setGrowthMode("value"); }, [viewMode]);

  const periods = store.periodsIS();
  const metrics = sortMetrics(store.metrics("income_statement"), IS_METRIC_ORDER);
  const rows: TableRow[] = metrics.map((key) => ({
    type: "data" as const,
    key,
    label: labelFor(key),
    vals: store.valMap("income_statement", key),
  }));

  const isGrowth = growthMode !== "value";
  const prevFn = growthMode === "qoq" ? prevQoQ : prevYoY;

  const chartData = {
    labels: periods,
    datasets: IS_CHART_METRICS
      .filter(({ key }) => metrics.includes(key))
      .map(({ key, label }, i) => {
        const vals = store.valMap("income_statement", key);
        return {
          label,
          data: isGrowth
            ? periods.map((p) => { const pk = prevFn(p); const g = growthPct(vals[p], pk ? vals[pk] : null); return g != null ? +(g * 100).toFixed(1) : null; })
            : periods.map((p) => vals[p] ?? null),
          borderColor: CHART_COLORS[i % CHART_COLORS.length],
          backgroundColor: CHART_COLORS[i % CHART_COLORS.length] + "cc",
          tension: 0.3,
          pointRadius: 3,
        };
      }),
  };

  return (
    <>
      <div className="mb-3">
        <GrowthToggle mode={growthMode} setMode={setGrowthMode} showQoQ={viewMode === "quarterly"} />
      </div>
      <div className="mb-4 rounded-md bg-[var(--bg-card)] p-4 shadow-sm">
        <div className="relative h-[320px]">
          <Line data={chartData} options={{
            responsive: true, maintainAspectRatio: false,
            interaction: { mode: "index" as const, intersect: false },
            plugins: {
              tooltip: { callbacks: { label: (ctx: any) => isGrowth ? `${ctx.dataset.label}: ${ctx.parsed.y?.toFixed(1)}%` : `${ctx.dataset.label}: $${ctx.parsed.y?.toLocaleString()}M` } },
              legend: { position: "bottom" as const, labels: { boxWidth: 12, font: { size: 11 } } },
            },
            scales: {
              x: { ticks: { font: { size: 10 }, maxRotation: 45 } },
              y: { ticks: { font: { size: 10 }, callback: (v: any) => isGrowth ? `${v}%` : `$${v}M` } },
            },
          }} />
        </div>
      </div>
      <DataTable periods={periods} rows={rows} store={store} growthMode={growthMode} />
    </>
  );
}

/* ================================================================
   Balance Sheet
   ================================================================ */
function BalanceSheet({ store }: { store: FactStore }) {
  const periods = store.periodsBS();
  const rows: TableRow[] = [];
  for (const [stmt, label, order] of [
    ["balance_sheet_assets", "ASSETS", BS_ASSETS_ORDER],
    ["balance_sheet_liabilities", "LIABILITIES", BS_LIABILITIES_ORDER],
    ["balance_sheet_equity", "EQUITY", BS_EQUITY_ORDER],
  ] as const) {
    const metrics = sortMetrics(store.metrics(stmt), order);
    if (!metrics.length) continue;
    rows.push({ type: "section", label });
    for (const key of metrics) {
      rows.push({ type: "data", key, label: labelFor(key), vals: store.valMap(stmt, key) });
    }
  }
  return <DataTable periods={periods} rows={rows} store={store} />;
}

/* ================================================================
   Cash Flow
   ================================================================ */
function CashFlowStatement({ store }: { store: FactStore }) {
  const periods = store.periodsIS();
  const rows: TableRow[] = [];
  for (const [stmt, label, order] of [
    ["cash_flow_operating", "OPERATING ACTIVITIES", CF_OPERATING_ORDER],
    ["cash_flow_investing", "INVESTING ACTIVITIES", CF_INVESTING_ORDER],
    ["cash_flow_financing", "FINANCING ACTIVITIES", CF_FINANCING_ORDER],
  ] as const) {
    const metrics = sortMetrics(store.metrics(stmt), order);
    if (!metrics.length) continue;
    rows.push({ type: "section", label });
    for (const key of metrics) {
      rows.push({ type: "data", key, label: labelFor(key), vals: store.valMap(stmt, key) });
    }
  }
  // Summary items
  const summaryMetrics = sortMetrics(store.metrics("cash_flow_summary"), CF_SUMMARY_ORDER);
  if (summaryMetrics.length) {
    rows.push({ type: "section", label: "SUMMARY" });
    for (const key of summaryMetrics) {
      rows.push({ type: "data", key, label: labelFor(key), vals: store.valMap("cash_flow_summary", key) });
    }
  }
  return <DataTable periods={periods} rows={rows} store={store} />;
}

/* ================================================================
   Ratios Panel
   ================================================================ */
function RatiosPanel({ store }: { store: FactStore }) {
  const periods = store.periods("financial_ratios");
  const allMetrics = store.metrics("financial_ratios");
  const [selected, setSelected] = useState<Set<string>>(
    () => new Set(["gross_margin_pct", "operating_margin_pct", "net_margin_pct"]),
  );

  if (!allMetrics.length)
    return <div className="p-10 text-center text-sm text-[#7f8c8d]">No financial ratios computed.</div>;

  const ordered = RATIO_ORDER.filter((k) => allMetrics.includes(k));
  for (const k of allMetrics) if (!ordered.includes(k)) ordered.push(k);

  const toggleMetric = (m: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(m)) next.delete(m); else next.add(m);
      return next;
    });
  };

  const selArr = ordered.filter((k) => selected.has(k));
  const usePercent = selArr.some((k) => isPct(k));

  const chartData = {
    labels: periods,
    datasets: selArr.map((key, i) => ({
      label: labelFor(key),
      data: periods.map((p) => store.val("financial_ratios", key, p)),
      borderColor: CHART_COLORS[i % CHART_COLORS.length],
      backgroundColor: CHART_COLORS[i % CHART_COLORS.length] + "22",
      tension: 0.3, pointRadius: 3, spanGaps: true,
    })),
  };

  return (
    <>
      <div className="mb-4 rounded-md bg-[var(--bg-card)] p-4 shadow-sm">
        <div className="mb-3 flex flex-wrap items-center gap-1.5">
          {ordered.map((key) => (
            <button key={key} onClick={() => toggleMetric(key)}
              className={`cursor-pointer rounded-full border px-3 py-1 text-xs transition-all select-none ${
                selected.has(key)
                  ? "border-[#1f4e79] bg-[#1f4e79] text-white"
                  : "border-[var(--border)] bg-[var(--bg-subtle)] text-[var(--text)] hover:border-[#2a6da8] hover:text-[#2a6da8]"
              }`}
            >
              {labelFor(key)}
            </button>
          ))}
        </div>
        <div className="relative h-[320px]">
          {selArr.length > 0 && <Line data={chartData} options={{
            responsive: true, maintainAspectRatio: false,
            interaction: { mode: "index" as const, intersect: false },
            plugins: {
              tooltip: { callbacks: { label: (ctx: any) => {
                const key = selArr[ctx.datasetIndex]; const v = ctx.parsed.y;
                if (v === null) return `${ctx.dataset.label}: —`;
                return isPct(key) ? `${ctx.dataset.label}: ${(v * 100).toFixed(1)}%` : `${ctx.dataset.label}: ${v.toFixed(2)}`;
              }}},
              legend: { position: "bottom" as const, labels: { boxWidth: 12, font: { size: 11 } } },
            },
            scales: {
              x: { ticks: { font: { size: 10 }, maxRotation: 45 } },
              y: { ticks: { font: { size: 10 }, callback: (v: any) => usePercent ? (v * 100).toFixed(0) + "%" : Number(v).toFixed(2) } },
            },
          }} />}
        </div>
      </div>
      <div className="overflow-x-auto rounded-md shadow-sm">
        <table className="w-full border-collapse bg-[var(--bg-card)] text-xs">
          <thead>
            <tr>
              <th className="sticky left-0 z-[11] min-w-[260px] border border-[var(--border)] bg-[#1f4e79] px-3 py-1.5 text-left font-semibold text-white">Metric</th>
              {periods.map((p) => {
                const end = store.periodEnd(p);
                return (
                  <th key={p} className="border border-[var(--border)] bg-[#1f4e79] px-3 py-1.5 text-center font-semibold text-white">
                    {p}{end && <span className="block text-[10px] font-normal text-white/70">{end}</span>}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {ordered.map((key, i) => {
              const isTotal = TOTAL_KEYS.has(key);
              const bgBase = isTotal ? "bg-[var(--bg-highlight)]" : i % 2 === 0 ? "bg-[var(--bg-subtle)]" : "bg-[var(--bg-card)]";
              const textCls = isTotal ? "font-bold text-[#7b3f00]" : "";
              const def = RATIO_DEFINITIONS[key];
              return (
                <tr key={key}>
                  <td className={`group sticky left-0 z-[5] border border-[var(--border)] px-3 py-1.5 text-left font-medium ${bgBase} ${textCls} relative cursor-help`}>
                    {labelFor(key)}
                    {def && <span className="pointer-events-none absolute left-full top-1/2 z-50 ml-2 hidden -translate-y-1/2 whitespace-nowrap rounded bg-[#2c3e50] px-2.5 py-1.5 text-[11px] font-normal text-white shadow-lg group-hover:block">{def}</span>}
                  </td>
                  {periods.map((p) => {
                    const v = store.val("financial_ratios", key, p);
                    const f = fmtVal(v, key, store.currency);
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
    </>
  );
}

/* ================================================================
   Segment Panel
   ================================================================ */
const SEG_LABELS: Record<string, string> = {
  revenue_by_business: "By Business",
  revenue_by_product: "By Product",
  revenue_by_geography: "By Geography",
};

function SegmentPanel({ store, viewMode }: { store: FactStore; viewMode: "quarterly" | "annual" }) {
  const categories = store.segmentCategories();
  const segOptions = categories.filter((c) => store.dimensions("segments", c).length > 0);

  const [segType, setSegType] = useState(segOptions[0] ?? "");
  const [growthMode, setGrowthMode] = useState<GrowthMode>("value");
  useEffect(() => { if (viewMode === "annual" && growthMode === "qoq") setGrowthMode("value"); }, [viewMode]);

  if (!segOptions.length)
    return <div className="p-10 text-center text-sm text-[#7f8c8d]">No segment data available for this ticker.</div>;

  const segData = store.segmentData(segType); // dimension → period → value
  const names = Object.keys(segData);
  const allPeriods = store.segmentPeriods(segType);
  const periods = viewMode === "annual"
    ? sortPeriods([...new Set(allPeriods.map((p) => { const m = p.match(/Q\d_FY(\d+)/); return m ? `FY${m[1]}` : p; }))])
    : allPeriods;

  // Build segVals: name → period → value (with annual aggregation if needed)
  const segVals: Record<string, Record<string, number | null>> = {};
  for (const name of names) {
    segVals[name] = {};
    if (viewMode === "annual") {
      // Aggregate quarterly to annual
      const fyMap: Record<string, number[]> = {};
      for (const [p, v] of Object.entries(segData[name])) {
        const m = p.match(/Q\d_FY(\d+)/);
        if (!m || v == null) continue;
        const fy = `FY${m[1]}`;
        if (!fyMap[fy]) fyMap[fy] = [];
        fyMap[fy].push(v);
      }
      for (const fy of periods) {
        const vals = fyMap[fy];
        segVals[name][fy] = vals?.length ? vals.reduce((a, b) => a + b, 0) : null;
      }
    } else {
      for (const p of periods) segVals[name][p] = segData[name][p] ?? null;
    }
  }

  const isGrowth = growthMode !== "value";
  const gPrevFn = growthMode === "qoq" ? prevQoQ : prevYoY;

  // Compute total row
  const totalVals: Record<string, number | null> = {};
  for (const p of periods) {
    const vals = names.map((n) => segVals[n][p]).filter((v): v is number => v != null);
    totalVals[p] = vals.length ? vals.reduce((a, b) => a + b, 0) : null;
  }

  const chartData = {
    labels: periods,
    datasets: names.map((name, i) => ({
      label: name,
      data: isGrowth
        ? periods.map((p) => { const pk = gPrevFn(p); const g = growthPct(segVals[name]?.[p], pk ? segVals[name]?.[pk] : null); return g != null ? +(g * 100).toFixed(1) : null; })
        : periods.map((p) => segVals[name]?.[p] ?? 0),
      borderColor: CHART_COLORS[i % CHART_COLORS.length],
      backgroundColor: CHART_COLORS[i % CHART_COLORS.length] + "cc",
      tension: 0.3, pointRadius: 3,
    })),
  };

  const renderRow = (label: string, vals: Record<string, number | null>, isTotal: boolean, idx: number) => {
    const bgBase = isTotal ? "bg-[var(--bg-highlight)]" : idx % 2 === 0 ? "bg-[var(--bg-subtle)]" : "bg-[var(--bg-card)]";
    return (
      <tr key={label}>
        <td className={`sticky left-0 z-[5] border border-[var(--border)] px-3 py-1.5 text-left font-medium whitespace-nowrap ${bgBase} ${isTotal ? "font-bold text-[#7b3f00]" : ""}`}>
          {label}
        </td>
        {periods.map((p) => {
          if (isGrowth) {
            const curr = vals[p];
            const pk = gPrevFn(p);
            const prev = pk ? vals[pk] : null;
            const g = growthPct(curr, prev);
            const f = fmtGrowth(g);
            return (
              <td key={p} className={`border border-[var(--border)] px-3 py-1.5 tabular-nums ${bgBase} ${
                f.cls === "negative" ? "text-right text-[#c0392b]" : f.cls === "positive" ? "text-right text-[#27ae60]" : f.cls === "null-val" ? "text-center text-[#7f8c8d]" : "text-right"
              }`}>{f.text}</td>
            );
          }
          const v = vals[p];
          const f = fmtVal(v, "revenue");
          return (
            <td key={p} className={`border border-[var(--border)] px-3 py-1.5 tabular-nums ${bgBase} ${isTotal ? "font-bold text-[#7b3f00]" : ""} ${
              f.cls === "negative" ? "text-right text-[#c0392b]" : f.cls === "null-val" ? "text-center text-[#7f8c8d]" : "text-right"
            }`}>{f.text}</td>
          );
        })}
      </tr>
    );
  };

  return (
    <>
      <div className="mb-3 flex items-center gap-4">
        <div className="flex gap-1">
          {segOptions.map((key) => (
            <button key={key} onClick={() => setSegType(key)}
              className={`rounded border px-3 py-1.5 text-xs font-semibold transition-all select-none ${
                segType === key ? "border-[var(--primary)] bg-[var(--primary)] text-white" : "border-[var(--border)] bg-[var(--bg-subtle)] text-[var(--text-muted)] hover:border-[var(--primary)]"
              }`}
            >{SEG_LABELS[key] || key}</button>
          ))}
        </div>
        <GrowthToggle mode={growthMode} setMode={setGrowthMode} showQoQ={viewMode === "quarterly"} />
      </div>

      <div className="mb-4 rounded-md bg-[var(--bg-card)] p-4 shadow-sm">
        <div className="relative h-[320px]">
          <Line data={chartData} options={{
            responsive: true, maintainAspectRatio: false,
            interaction: { mode: "index" as const, intersect: false },
            plugins: {
              tooltip: { callbacks: { label: (ctx: any) => isGrowth ? `${ctx.dataset.label}: ${ctx.parsed.y?.toFixed(1)}%` : `${ctx.dataset.label}: $${ctx.parsed.y}M` } },
              legend: { position: "bottom" as const, labels: { boxWidth: 12, font: { size: 11 } } },
            },
            scales: {
              x: { ticks: { font: { size: 10 }, maxRotation: 45 } },
              y: { ticks: { font: { size: 10 }, callback: (v: any) => isGrowth ? `${v}%` : `$${v}M` } },
            },
          }} />
        </div>
      </div>

      <SegmentPieChart segVals={segVals} periods={periods} />

      <div className="overflow-x-auto rounded-md shadow-sm">
        <table className="w-full border-collapse bg-[var(--bg-card)] text-xs">
          <thead>
            <tr>
              <th className="sticky left-0 z-[11] min-w-[180px] border border-[var(--border)] bg-[#1f4e79] px-3 py-1.5 text-left font-semibold text-white">Segment</th>
              {periods.map((p) => (
                <th key={p} className="border border-[var(--border)] bg-[#1f4e79] px-3 py-1.5 text-center font-semibold text-white whitespace-nowrap">{p}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {names.map((seg, i) => renderRow(seg, segVals[seg], false, i))}
            {renderRow("Total", totalVals, true, names.length)}
          </tbody>
        </table>
      </div>
      <div className="mt-2 text-right text-[10px] text-[var(--text-faint)]">Source: NotebookLM / SEC EDGAR · Unit: $M</div>
    </>
  );
}

/* ================================================================
   Non-GAAP Panel
   ================================================================ */
function NonGaapPanel({ store, viewMode }: { store: FactStore; viewMode: "quarterly" | "annual" }) {
  const ngMetrics = store.nonGaapMetrics();
  if (!ngMetrics.length)
    return <div className="p-10 text-center text-sm text-[#7f8c8d]">No Non-GAAP data available for this ticker.</div>;

  const adjEps = store.nonGaapValMap("adjusted_eps_diluted");
  if (!Object.keys(adjEps).length)
    return <div className="p-10 text-center text-sm text-[#7f8c8d]">No adjusted EPS data available.</div>;

  const allPeriods = sortPeriods(Object.keys(adjEps));
  const quarterlyPeriods = allPeriods.filter((p) => p.startsWith("Q"));
  const annualPeriods = allPeriods.filter((p) => p.startsWith("FY"));
  const gaapEps = store.valMap("income_statement", "eps_diluted");

  const renderTable = (periods: string[], label: string) => (
    <>
      <div className="mb-2 text-xs font-semibold text-[var(--text-muted)]">{label}</div>
      <div className="mb-4 overflow-x-auto rounded-md shadow-sm">
        <table className="w-full border-collapse bg-[var(--bg-card)] text-xs">
          <thead>
            <tr>
              <th className="sticky left-0 z-[11] min-w-[200px] border border-[var(--border)] bg-[#1f4e79] px-3 py-1.5 text-left font-semibold text-white">Metric</th>
              {periods.map((p) => (
                <th key={p} className="border border-[var(--border)] bg-[#1f4e79] px-3 py-1.5 text-center font-semibold text-white whitespace-nowrap">{p}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {/* GAAP EPS */}
            <tr>
              <td className="sticky left-0 z-[5] border border-[var(--border)] bg-[var(--bg-subtle)] px-3 py-1.5 text-left font-medium">GAAP EPS (Diluted)</td>
              {periods.map((p) => {
                const v = gaapEps[p];
                return (
                  <td key={p} className={`border border-[var(--border)] bg-[var(--bg-subtle)] px-3 py-1.5 text-right tabular-nums ${v != null && v < 0 ? "text-[#c0392b]" : ""}`}>
                    {v != null ? `$${Number(v).toFixed(2)}` : "—"}
                  </td>
                );
              })}
            </tr>
            {/* Non-GAAP EPS */}
            <tr>
              <td className="sticky left-0 z-[5] border border-[var(--border)] bg-[var(--bg-card)] px-3 py-1.5 text-left font-medium">Adjusted EPS (Non-GAAP)</td>
              {periods.map((p) => {
                const v = adjEps[p];
                return (
                  <td key={p} title={store.nonGaapSource("adjusted_eps_diluted", p) || ""}
                    className={`border border-[var(--border)] bg-[var(--bg-card)] px-3 py-1.5 text-right tabular-nums ${v != null && v < 0 ? "text-[#c0392b]" : ""}`}>
                    {v != null ? `$${Number(v).toFixed(2)}` : "—"}
                  </td>
                );
              })}
            </tr>
            {/* Delta */}
            <tr>
              <td className="sticky left-0 z-[5] border border-[var(--border)] bg-[var(--bg-highlight)] px-3 py-1.5 text-left font-bold text-[#7b3f00]">Δ (Non-GAAP − GAAP)</td>
              {periods.map((p) => {
                const gaap = gaapEps[p];
                const ng = adjEps[p];
                const delta = gaap != null && ng != null ? ng - gaap : null;
                return (
                  <td key={p} className={`border border-[var(--border)] bg-[var(--bg-highlight)] px-3 py-1.5 text-right font-bold tabular-nums ${
                    delta != null && delta < 0 ? "text-[#c0392b]" : delta != null && delta > 0 ? "text-[#27ae60]" : "text-[#7b3f00]"
                  }`}>
                    {delta != null ? `${delta >= 0 ? "+" : ""}${delta.toFixed(2)}` : "—"}
                  </td>
                );
              })}
            </tr>
          </tbody>
        </table>
      </div>
    </>
  );

  return (
    <div>
      <h3 className="mb-3 text-sm font-bold text-[var(--text)]">Adjusted EPS (Diluted) — GAAP vs Non-GAAP</h3>
      {quarterlyPeriods.length > 0 && renderTable(quarterlyPeriods, "Quarterly")}
      {annualPeriods.length > 0 && renderTable(annualPeriods, "Annual")}
      <div className="mt-2 text-[10px] text-[var(--text-faint)]">
        Source: NotebookLM (SEC filings / earnings call transcripts) · hover over cells for detailed source
      </div>
    </div>
  );
}

/* ================================================================
   Main Viewer
   ================================================================ */
const TABS = [
  { id: "is", label: "Income Statement" },
  { id: "bs", label: "Balance Sheet" },
  { id: "cf", label: "Cash Flow" },
  { id: "ratios", label: "Financial Ratios" },
  { id: "segments", label: "Segments" },
  { id: "non-gaap", label: "Non-GAAP" },
];

export default function Viewer() {
  const [tickers, setTickers] = useState<string[]>([]);
  const [ticker, setTicker] = useState("");
  const [tab, setTab] = useState("is");
  const [viewMode, setViewMode] = useState<"quarterly" | "annual">("quarterly");

  useEffect(() => {
    fetch("/data/financials/tickers.json")
      .then((r) => r.json())
      .then(setTickers)
      .catch(() => setTickers(["SNDK", "MU", "LEU"]));
  }, []);

  const { store: rawStore, loading } = useFinancialData(ticker);

  const store = useMemo(() => {
    if (!rawStore) return null;
    return viewMode === "annual" ? rawStore.toAnnual() : rawStore;
  }, [rawStore, viewMode]);

  const meta = rawStore?.company;

  return (
    <div className="min-h-screen bg-[var(--bg-page)]">
      <div className="sticky top-0 z-50 flex items-center gap-4 bg-[#1f4e79] px-6 py-3 text-white shadow-md">
        <Link href="/" className="text-sm text-white opacity-70 transition-opacity hover:opacity-100">← Portal</Link>
        <h1 className="text-base font-semibold whitespace-nowrap">Financials Viewer</h1>
        <select
          value={ticker}
          onChange={(e) => setTicker(e.target.value)}
          className="cursor-pointer rounded border-none bg-white/15 px-3 py-1.5 text-sm font-semibold text-white [&>option]:bg-[var(--bg-card)] [&>option]:text-[var(--text)]"
        >
          <option value="">-- Select Ticker --</option>
          {tickers.map((t) => (
            <option key={t} value={t}>{TICKER_LABELS[t] ? `${t} ${TICKER_LABELS[t]}` : t}</option>
          ))}
        </select>
        <div className="ml-4 flex">
          {(["quarterly", "annual"] as const).map((m) => (
            <button key={m} onClick={() => setViewMode(m)}
              className={`cursor-pointer border border-white/30 px-3.5 py-1 text-xs font-semibold transition-all first:rounded-l last:rounded-r last:border-l-0 ${
                viewMode === m ? "bg-white/20 text-white" : "text-white/70"
              }`}
            >{m === "quarterly" ? "Quarterly" : "Annual"}</button>
          ))}
        </div>
        <ThemeToggle />
        {meta && (
          <div className="ml-auto text-xs text-white/70">
            {meta.company}{meta.exchange ? ` | ${meta.exchange}` : ""} | {meta.currency || "USD"} | Updated: {meta.last_updated}
          </div>
        )}
      </div>

      <div className="sticky top-[48px] z-40 flex gap-0 border-b-2 border-[var(--border)] bg-[var(--bg-card)] px-6">
        {TABS.map((t) => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`-mb-0.5 cursor-pointer border-b-2 px-5 py-2.5 text-[13px] font-medium transition-all select-none ${
              tab === t.id ? "border-[#1f4e79] font-bold text-[#1f4e79]" : "border-transparent text-[#7f8c8d] hover:text-[#2a6da8]"
            }`}
          >{t.label}</button>
        ))}
      </div>

      <div className="mx-auto max-w-full overflow-x-auto p-4 px-6">
        {loading && <div className="py-16 text-center text-sm text-[#7f8c8d]">Loading...</div>}
        {!loading && !store && <div className="py-16 text-center text-sm text-[#7f8c8d]">Select a ticker to view financial statements.</div>}
        {!loading && store && (
          <>
            {tab === "is" && <IncomeStatement store={store} viewMode={viewMode} />}
            {tab === "bs" && <BalanceSheet store={store} />}
            {tab === "cf" && <CashFlowStatement store={store} />}
            {tab === "ratios" && <RatiosPanel store={store} />}
            {tab === "segments" && <SegmentPanel store={store} viewMode={viewMode} />}
            {tab === "non-gaap" && <NonGaapPanel store={store} viewMode={viewMode} />}
          </>
        )}
      </div>
    </div>
  );
}
