"use client";

/* eslint-disable @typescript-eslint/no-explicit-any */
import React, { useState, useEffect, useMemo } from "react";
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
import ValuationChart from "@/app/components/financials/ValuationChart";
import {
  TICKER_LABELS, TOTAL_KEYS, SUBTOTAL_KEYS, RATIO_CATEGORIES, RATIO_DEFINITIONS, CHART_COLORS,
  sortPeriods, isPct, isEps, fmtVal, labelFor, sortMetrics,
  IS_METRIC_ORDER, US_IS_METRIC_ORDER, IS_PCT_EXCLUDE, IS_HIDDEN,
  BS_ASSETS_ORDER, BS_LIABILITIES_ORDER, BS_EQUITY_ORDER,
  CF_OPERATING_ORDER, CF_INVESTING_ORDER, CF_FINANCING_ORDER, CF_SUMMARY_ORDER,
  prevQoQ, prevYoY, growthPct, fmtGrowth, skipGrowthForKey,
  type GrowthMode,
} from "@/app/components/financials/constants";
import { useFinancialData } from "@/app/components/financials/useFinancialData";
import { FactStore, type NoteMap, type ValMap } from "@/app/components/financials/FactStore";

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

function CellNoteMarker({ note, symbol, tone }: { note: string; symbol: string; tone: "derived" | "info" }) {
  const colorClass = tone === "derived" ? "text-amber-500" : "text-sky-600";
  return (
    <span className="group relative ml-1 inline-flex cursor-help items-center align-super">
      <span className={`text-[10px] font-semibold ${colorClass}`}>{symbol}</span>
      <span className="pointer-events-none absolute bottom-full left-1/2 z-50 mb-1 hidden w-56 -translate-x-1/2 rounded bg-[#2c3e50] px-2 py-1.5 text-left text-[11px] font-normal leading-snug text-white shadow-lg group-hover:block">
        {note}
      </span>
    </span>
  );
}

/* ── Row types for table rendering ── */
type TableRow =
  | { type: "section"; label: string }
  | { type: "data"; key: string; label: React.ReactNode; vals: ValMap; notes?: NoteMap; indent?: boolean; derivedPeriods?: Set<string> };

/* ── Generic data table ── */
const CHART_NON_SELECTABLE = new Set([
  "weighted_avg_shares_basic", "weighted_avg_shares_diluted",
]);

function DataTable({
  periods,
  rows,
  store,
  growthMode = "value",
  onRowClick,
  chartMetrics,
}: {
  periods: string[];
  rows: TableRow[];
  store: FactStore;
  growthMode?: GrowthMode;
  onRowClick?: (key: string) => void;
  chartMetrics?: string[];
}) {
  if (!rows.length) return <div className="p-10 text-center text-sm text-[#7f8c8d]">No data available.</div>;

  const isGrowth = growthMode !== "value";
  const prevFn = growthMode === "qoq" ? prevQoQ : prevYoY;

  const isChartable = (key: string) =>
    !!onRowClick && !isPct(key) && !isEps(key) && !key.startsWith("_") && !CHART_NON_SELECTABLE.has(key);

  return (
    <div className="overflow-x-auto rounded-md shadow-sm">
      <table className="w-full border-separate border-spacing-0 bg-[var(--bg-card)] text-xs">
        <thead>
          <tr>
            <th className="sticky left-0 z-[11] min-w-[260px] border border-[var(--border)] bg-[#1f4e79] px-3 py-1.5 text-left font-semibold text-white">
              Metric
            </th>
            {periods.map((p) => {
              const end = store.periodEnd(p);
              const qCount = store.incompleteFYQuarters(p);
              return (
                <th key={p} className="border-t border-b border-r border-[var(--border)] bg-[#1f4e79] px-3 py-1.5 text-center font-semibold text-white">
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
                    className="border-b border-x border-[var(--border)] bg-[#d6e4f0] px-3 py-1.5 text-[11px] font-bold uppercase tracking-wide text-[#1f4e79]"
                  >
                    {row.label}
                  </td>
                </tr>
              );
            }
            const isTotal = TOTAL_KEYS.has(row.key);
            const isSubtotal = SUBTOTAL_KEYS.has(row.key);
            const isRatioRow = isPct(row.key) && !isTotal;
            const isEpsRow = isEps(row.key);
            const bgBase = isEpsRow  ? "bg-[#1f4e79]"
              : isTotal              ? "bg-[var(--bg-highlight)]"
              : isSubtotal           ? "bg-[#e8f4fd]"
              : isRatioRow           ? "bg-[var(--bg-card)]"
              : "bg-[var(--bg-card)]";
            const textCls = isEpsRow ? "font-bold text-white"
              : isTotal              ? "font-bold text-[#7b3f00]"
              : isSubtotal           ? "font-semibold text-[#1565c0] dark:text-blue-300"
              : isRatioRow           ? "text-[#aaa] dark:text-[#888]"
              : "";
            const skipGrowth = isGrowth && skipGrowthForKey(row.key);
            const chartIdx = chartMetrics ? chartMetrics.indexOf(row.key) : -1;
            const isSelected = chartIdx >= 0;
            const clickable = isChartable(row.key);
            return (
              <tr
                key={row.key + i}
                onClick={clickable ? () => onRowClick!(row.key) : undefined}
                className={clickable ? "cursor-pointer" : ""}
              >
                <td className={`sticky left-0 z-[10] border-l border-b border-r border-[var(--border)] py-1.5 text-left font-medium ${bgBase} ${textCls} ${row.indent ? "pl-8 pr-3 italic text-[#555]" : "px-3"}`}>
                  {isSelected ? (
                    <span className="flex items-center gap-1.5">
                      <span className="shrink-0 h-2 w-2 rounded-sm" style={{ backgroundColor: CHART_COLORS[chartIdx % CHART_COLORS.length] }} />
                      <span>{row.label}</span>
                    </span>
                  ) : row.label}
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
                        className={`border-b border-r border-[var(--border)] px-3 py-1.5 tabular-nums ${bgBase} ${
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
                  const isDerived = row.derivedPeriods?.has(p) ?? false;
                  const note = row.notes?.[p] ?? null;
                  return (
                    <td
                      key={p}
                      className={`border-b border-r border-[var(--border)] px-3 py-1.5 tabular-nums ${bgBase} ${textCls} ${
                        f.cls === "negative" ? "text-right text-[#c0392b]" : f.cls === "null-val" ? "text-center text-[#7f8c8d]" : "text-right"
                      }`}
                      title={note ?? (isDerived ? "Derived value" : undefined)}
                    >
                      {f.text}
                      {isDerived && f.cls !== "null-val" && (
                        <CellNoteMarker note={note ?? "Derived value"} symbol="*" tone="derived" />
                      )}
                      {!isDerived && note && f.cls !== "null-val" && (
                        <CellNoteMarker note={note} symbol="†" tone="info" />
                      )}
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
// 圖表預設指標（按優先順序，取前 3 個有資料的）
const CHART_DEFAULT_CANDIDATES = [
  "operating_revenue", "revenue",
  "gross_profit",
  "operating_income",
  "net_income",
];

// Sub-items: metrics that are sub-components of another line, shown as indented toggles
const IS_SUB_ITEMS: Record<string, string[]> = {
  // 其他綜合損益兩大類 toggle（IFRS 通用，適用所有台股）
  oci_not_reclassified: ["oci_fvoci_equity"],          // 8310 不重分類至損益之項目
  oci_reclassified:     ["oci_fx_translation"],         // 8360 後續可能重分類至損益之項目
  // 非營業收支（美股舊格式）
  other_nonoperating_income_expense: ["equity_method_investments", "equity_in_net_income_of_investees"],
};

function IncomeStatement({ store, viewMode }: { store: FactStore; viewMode: "quarterly" | "annual" }) {
  const [growthMode, setGrowthMode] = useState<GrowthMode>("value");
  useEffect(() => { if (viewMode === "annual" && growthMode === "qoq") setGrowthMode("value"); }, [viewMode]);
  const [expandedSubs, setExpandedSubs] = useState<Set<string>>(new Set());
  const toggleSub = (key: string) => setExpandedSubs((prev) => {
    const next = new Set(prev);
    if (next.has(key)) next.delete(key); else next.add(key);
    return next;
  });

  const periods = (viewMode === "annual" ? store.periodsIS().filter((p) => /^FY\d+$/.test(p)) : store.periodsIS().filter((p) => /^Q\d_FY\d+$/.test(p)));
  const isMetrics = store.metrics("income_statement");

  // 圖表選取狀態：最多 3 個，超過時踢掉最舊的
  const [chartMetrics, setChartMetrics] = useState<string[]>(() =>
    CHART_DEFAULT_CANDIDATES.filter(k => isMetrics.includes(k)).slice(0, 3)
  );
  const toggleChartMetric = (key: string) => {
    setChartMetrics(prev => {
      if (prev.includes(key)) return prev.filter(k => k !== key);
      const next = [...prev, key];
      if (next.length > 3) next.shift(); // 超過 3 個：移除最舊
      return next;
    });
  };
  const IS_SUB_SET = new Set(Object.values(IS_SUB_ITEMS).flat());
  const ticker = store.company?.ticker;
  const metricOrder = store.currency === "TWD" ? IS_METRIC_ORDER : US_IS_METRIC_ORDER;
  const metrics = sortMetrics(
    isMetrics.filter((m) => !IS_PCT_EXCLUDE.has(m) && !IS_HIDDEN.has(m) && !IS_SUB_SET.has(m)),
    metricOrder,
  );
  const rows: TableRow[] = metrics.map((key) => {
    const subKeys = (IS_SUB_ITEMS[key] ?? []).filter((m) => isMetrics.includes(m));
    const hasSubItems = subKeys.length > 0;
    const isExpanded = expandedSubs.has(key);
    const label = hasSubItems ? (
      <button
        onClick={(e) => { e.stopPropagation(); toggleSub(key); }}
        className="flex items-center gap-1 text-left hover:text-[#1f4e79]"
      >
        <span className="text-[10px] text-[#7f8c8d]">{isExpanded ? "▼" : "▶"}</span>
        {labelFor(key, store.currency, ticker)}
      </button>
    ) : labelFor(key, store.currency, ticker);
    const IS_ANNUAL_ONLY_METRICS = new Set([
      "weighted_avg_shares_basic", "weighted_avg_shares_diluted",
    ]);
    const rawVals = store.valMap("income_statement", key);
    const derivedPeriods = new Set<string>();
    const vals = IS_ANNUAL_ONLY_METRICS.has(key) && viewMode === "quarterly"
      ? Object.fromEntries(periods.map((p) => {
          if (key === "weighted_avg_shares_basic" || key === "weighted_avg_shares_diluted") {
            const derivedMetric = key === "weighted_avg_shares_basic"
              ? "weighted_avg_shares_basic_derived"
              : "weighted_avg_shares_diluted_derived";
            const derived = p.startsWith("Q4_") ? store.val("financial_ratios", derivedMetric, p) : null;
            if (derived != null) derivedPeriods.add(p);
            return [p, derived ?? (p.startsWith("Q4_") ? null : (rawVals[p] ?? null))];
          }
          return [p, p.startsWith("Q4_") ? null : (rawVals[p] ?? null)];
        }))
      : rawVals;
    return { type: "data" as const, key, label, vals, notes: store.noteMap("income_statement", key), derivedPeriods };
  });

  // Inject sub-item rows after parent rows (only when expanded)
  for (const [parentKey, subKeys] of Object.entries(IS_SUB_ITEMS)) {
    if (!expandedSubs.has(parentKey)) continue;
    const parentIdx = rows.findIndex((r) => r.type === "data" && r.key === parentKey);
    if (parentIdx < 0) continue;
    const presentSubs = subKeys.filter((m) => isMetrics.includes(m));
    const toInsert: TableRow[] = presentSubs.map((m) => ({
      type: "data" as const, key: m, label: labelFor(m, store.currency, ticker),
      vals: store.valMap("income_statement", m), notes: store.noteMap("income_statement", m), indent: true,
    }));

    // Compute residual: parent − Σ sub-items (per period)
    const parentVals = store.valMap("income_statement", parentKey);
    const residualVals: ValMap = {};
    let hasResidual = false;
    for (const p of periods) {
      const parentV = parentVals[p];
      const subSum = presentSubs.reduce<number | null>((acc, m) => {
        const v = store.val("income_statement", m, p);
        return v != null ? (acc ?? 0) + v : acc;
      }, null);
      if (parentV != null && subSum != null) {
        const residual = Math.round((parentV - subSum) * 100) / 100;
        residualVals[p] = Math.abs(residual) > 0.01 ? residual : null;
        if (residualVals[p] != null) hasResidual = true;
      } else {
        residualVals[p] = null;
      }
    }
    if (hasResidual) {
      toInsert.push({ type: "data" as const, key: `_residual_${parentKey}`, label: "Other", vals: residualVals, indent: true });
    }

    rows.splice(parentIdx + 1, 0, ...toInsert);
  }

  // Synthetic total: sources are [metric, sign] pairs — sign handles stored-positive expenses
  const syntheticSum = (sources: [string, number][]): Record<string, number | null> => {
    const present = sources.filter(([m]) => isMetrics.includes(m));
    const result: Record<string, number | null> = {};
    for (const p of periods) {
      let total: number | null = null;
      for (const [m, sign] of present) {
        const v = store.val("income_statement", m, p);
        if (v !== null) total = (total ?? 0) + sign * v;
      }
      result[p] = total;
    }
    return result;
  };


  const isGrowth = growthMode !== "value";
  const prevFn = growthMode === "qoq" ? prevQoQ : prevYoY;
  const isTWD = store.currency === "TWD";

  // TWD 單位：千元 → 以百萬元顯示（÷1000）
  const fmtChartVal = (v: number) =>
    isTWD ? `NT$${Math.round(v / 1000).toLocaleString()}M` : `$${v.toLocaleString()}M`;

  const chartData = {
    labels: periods,
    datasets: chartMetrics
      .filter(key => isMetrics.includes(key))
      .map((key, i) => {
        const vals = store.valMap("income_statement", key);
        return {
          label: labelFor(key, store.currency, ticker),
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
        <p className="mb-1 text-[10px] text-[var(--text-muted)]">點擊下方表格列可加入／移除圖表（最多 3 個）</p>
        <div className="relative h-[300px]">
          <Line data={chartData} options={{
            responsive: true, maintainAspectRatio: false,
            interaction: { mode: "index" as const, intersect: false },
            plugins: {
              tooltip: { callbacks: { label: (ctx: any) => isGrowth ? `${ctx.dataset.label}: ${ctx.parsed.y?.toFixed(1)}%` : `${ctx.dataset.label}: ${fmtChartVal(ctx.parsed.y)}` } },
              legend: { position: "bottom" as const, labels: { boxWidth: 12, font: { size: 11 } } },
            },
            scales: {
              x: { ticks: { font: { size: 10 }, maxRotation: 45 } },
              y: { ticks: { font: { size: 10 }, callback: (v: any) => isGrowth ? `${v}%` : fmtChartVal(v) } },
            },
          }} />
        </div>
      </div>
      <DataTable periods={periods} rows={rows} store={store} growthMode={growthMode} onRowClick={toggleChartMetric} chartMetrics={chartMetrics} />
      {viewMode === "quarterly" && (isMetrics.includes("weighted_avg_shares_basic") || isMetrics.includes("weighted_avg_shares_diluted")) && (
        <p className="mt-2 text-[11px] text-[var(--text-muted)]">
          Q4 weighted-average shares are shown as <span className="font-semibold">derived</span> values from `financial_metrics` when the annual report only discloses full-year share counts.
        </p>
      )}
    </>
  );
}

/* ================================================================
   Balance Sheet
   ================================================================ */
function BalanceSheet({ store, viewMode }: { store: FactStore; viewMode: "quarterly" | "annual" }) {
  const periods = (viewMode === "annual" ? store.periodsBS().filter((p) => /^FY\d+$/.test(p)) : store.periodsBS().filter((p) => /^Q\d_FY\d+$/.test(p)));
  const ticker = store.company?.ticker;
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
      rows.push({ type: "data", key, label: labelFor(key, store.currency, ticker), vals: store.valMap(stmt, key), notes: store.noteMap(stmt, key) });
    }
  }
  return <DataTable periods={periods} rows={rows} store={store} />;
}

/* ================================================================
   Cash Flow
   ================================================================ */
function CashFlowStatement({ store, viewMode }: { store: FactStore; viewMode: "quarterly" | "annual" }) {
  const periods = (viewMode === "annual" ? store.periodsIS().filter((p) => /^FY\d+$/.test(p)) : store.periodsIS().filter((p) => /^Q\d_FY\d+$/.test(p)));
  const ticker = store.company?.ticker;
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
      rows.push({ type: "data", key, label: labelFor(key, store.currency, ticker), vals: store.valMap(stmt, key), notes: store.noteMap(stmt, key) });
    }
  }
  // Summary items
  const summaryMetrics = sortMetrics(store.metrics("cash_flow_summary"), CF_SUMMARY_ORDER);
  if (summaryMetrics.length) {
    rows.push({ type: "section", label: "SUMMARY" });
    for (const key of summaryMetrics) {
      rows.push({ type: "data", key, label: labelFor(key, store.currency, ticker), vals: store.valMap("cash_flow_summary", key), notes: store.noteMap("cash_flow_summary", key) });
    }
  }
  return <DataTable periods={periods} rows={rows} store={store} />;
}

/* ================================================================
   Ratios Panel
   ================================================================ */
function RatiosPanel({ store, viewMode }: { store: FactStore; viewMode: "quarterly" | "annual" }) {
  const ticker = store.company?.ticker;
  // financial_ratios covers most metrics; effective_tax_rate falls back to income_statement
  const ratioMetrics = store.metrics("financial_ratios");
  const isMetrics = store.metrics("income_statement");
  const periods = (viewMode === "annual" ? store.periodsIS().filter((p) => /^FY\d+$/.test(p)) : store.periodsIS().filter((p) => /^Q\d_FY\d+$/.test(p)));

  // Lookup: financial_ratios first, then income_statement fallback
  const ratioVal = (key: string, p: string): number | null => {
    const v1 = store.val("financial_ratios", key, p);
    if (v1 != null) return v1;
    return store.val("income_statement", key, p);
  };

  // Build available categories (only include metrics present in data)
  const availCats = RATIO_CATEGORIES.map((cat) => ({
    ...cat,
    metrics: cat.metrics.filter((m) =>
      ratioMetrics.includes(m) || (m === "effective_tax_rate" && isMetrics.includes("effective_tax_rate"))
    ),
  })).filter((cat) => cat.metrics.length > 0);

  const allAvail = availCats.flatMap((c) => c.metrics);

  const [selected, setSelected] = useState<Set<string>>(
    () => new Set(["gross_margin_pct", "operating_margin_pct", "net_margin_pct"]),
  );

  if (!allAvail.length)
    return <div className="p-10 text-center text-sm text-[#7f8c8d]">No financial ratios computed.</div>;

  const toggleMetric = (m: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(m)) next.delete(m); else next.add(m);
      return next;
    });
  };

  const selArr = allAvail.filter((k) => selected.has(k));
  const usePercent = selArr.some((k) => isPct(k));

  const chartData = {
    labels: periods,
    datasets: selArr.map((key, i) => ({
      label: labelFor(key, store.currency, ticker),
      data: periods.map((p) => ratioVal(key, p)),
      borderColor: CHART_COLORS[i % CHART_COLORS.length],
      backgroundColor: CHART_COLORS[i % CHART_COLORS.length] + "22",
      tension: 0.3, pointRadius: 3, spanGaps: true,
    })),
  };

  return (
    <>
      <div className="mb-4 rounded-md bg-[var(--bg-card)] p-4 shadow-sm">
        {/* Category-grouped metric selectors */}
        <div className="mb-4 space-y-2">
          {availCats.map((cat) => (
            <div key={cat.label} className="flex flex-wrap items-center gap-1.5">
              <span className="w-24 shrink-0 text-[10px] font-semibold uppercase tracking-wide text-[#7f8c8d]">{cat.label}</span>
              {cat.metrics.map((key) => (
                <button key={key} onClick={() => toggleMetric(key)}
                  className={`cursor-pointer rounded-full border px-3 py-1 text-xs transition-all select-none ${
                    selected.has(key)
                      ? "border-[#1f4e79] bg-[#1f4e79] text-white"
                      : "border-[var(--border)] bg-[var(--bg-subtle)] text-[var(--text)] hover:border-[#2a6da8] hover:text-[#2a6da8]"
                  }`}
                >
                  {labelFor(key, store.currency, ticker)}
                </button>
              ))}
            </div>
          ))}
        </div>
        <div className="relative h-[280px]">
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
          {!selArr.length && <div className="flex h-full items-center justify-center text-sm text-[#7f8c8d]">Select metrics above to chart</div>}
        </div>
      </div>

      {/* Table with category section headers */}
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
            {availCats.map((cat) => (
              <React.Fragment key={cat.label}>
                <tr>
                  <td colSpan={periods.length + 1}
                    className="border border-[var(--border)] bg-[#2c3e50] px-3 py-1 text-[11px] font-semibold uppercase tracking-wide text-white/80">
                    {cat.label}
                  </td>
                </tr>
                {cat.metrics.map((key, i) => {
                  const def = RATIO_DEFINITIONS[key];
                  const bgBase = i % 2 === 0 ? "bg-[var(--bg-subtle)]" : "bg-[var(--bg-card)]";
                  return (
                    <tr key={key}>
                      <td className={`group sticky left-0 z-[10] border border-[var(--border)] px-3 py-1.5 text-left font-medium ${bgBase} relative cursor-help`}>
                        {labelFor(key, store.currency, ticker)}
                        {def && <span className="pointer-events-none absolute left-full top-1/2 z-50 ml-2 hidden -translate-y-1/2 whitespace-nowrap rounded bg-[#2c3e50] px-2.5 py-1.5 text-[11px] font-normal text-white shadow-lg group-hover:block">{def}</span>}
                      </td>
                      {periods.map((p) => {
                        const v = ratioVal(key, p);
                        const f = fmtVal(v, key, store.currency);
                        return (
                          <td key={p} className={`border border-[var(--border)] px-3 py-1.5 tabular-nums ${bgBase} ${
                            f.cls === "negative" ? "text-right text-[#c0392b]" : f.cls === "null-val" ? "text-center text-[#7f8c8d]" : "text-right"
                          }`}>{f.text}</td>
                        );
                      })}
                    </tr>
                  );
                })}
              </React.Fragment>
            ))}
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
  profit_by_business: "By Business Profit",
  revenue_by_product: "By Product",
  revenue_by_geography: "By Geography",
};

const ALL_SEGMENTS_KEY = "__all__";

function segmentLabel(key: string) {
  if (SEG_LABELS[key]) return SEG_LABELS[key];
  return key
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function buildSegmentCategoryVals(
  store: FactStore,
  category: string,
  viewMode: "quarterly" | "annual",
) {
  const segData = store.segmentData(category);
  const names = Object.keys(segData);
  const allPeriods = store.segmentPeriods(category);
  const quarterlyPeriods = sortPeriods(allPeriods.filter((p) => /^Q\d_FY\d+$/.test(p)));
  const annualDirectPeriods = sortPeriods(allPeriods.filter((p) => /^FY\d+$/.test(p)));
  const periods = viewMode === "annual"
    ? sortPeriods([...new Set([
        ...annualDirectPeriods,
        ...quarterlyPeriods.map((p) => {
          const m = p.match(/Q\d_FY(\d+)/);
          return m ? `FY${m[1]}` : p;
        }),
      ])])
    : quarterlyPeriods;

  const segVals: Record<string, Record<string, number | null>> = {};
  for (const name of names) {
    segVals[name] = {};
    if (viewMode === "annual") {
      const fyMap: Record<string, number[]> = {};
      const directAnnual: Record<string, number> = {};
      for (const [p, v] of Object.entries(segData[name])) {
        if (v == null) continue;
        const direct = p.match(/^FY(\d+)$/);
        if (direct) {
          directAnnual[`FY${direct[1]}`] = v;
          continue;
        }
        const m = p.match(/Q\d_FY(\d+)/);
        if (!m) continue;
        const fy = `FY${m[1]}`;
        if (!fyMap[fy]) fyMap[fy] = [];
        fyMap[fy].push(v);
      }
      for (const fy of periods) {
        if (directAnnual[fy] != null) {
          segVals[name][fy] = directAnnual[fy];
          continue;
        }
        const vals = fyMap[fy];
        segVals[name][fy] = vals?.length ? vals.reduce((a, b) => a + b, 0) : null;
      }
    } else {
      for (const p of periods) segVals[name][p] = segData[name][p] ?? null;
    }
  }

  return { names, periods, segVals };
}

function SegmentCategorySection({
  store,
  viewMode,
  category,
  growthMode,
  showTitle = true,
}: {
  store: FactStore;
  viewMode: "quarterly" | "annual";
  category: string;
  growthMode: GrowthMode;
  showTitle?: boolean;
}) {
  const { names, periods, segVals } = buildSegmentCategoryVals(store, category, viewMode);
  const allPeriods = store.segmentPeriods(category);
  const samplePeriod = allPeriods[0] ?? "";
  const sampleName = names[0] ?? "";
  const segmentUnit = samplePeriod && sampleName ? store.unit("segments", category, samplePeriod, sampleName) : null;

  const formatSegmentValue = (value: number) => {
    if (segmentUnit === "TWD_thousands") return `NT$ ${value.toLocaleString("en-US")} 千元`;
    if (segmentUnit === "USD_thousands") return `$ ${value.toLocaleString("en-US")}k`;
    return value.toLocaleString("en-US");
  };

  const segmentTickLabel = (value: number | string) => {
    const n = typeof value === "number" ? value : Number(value);
    if (Number.isNaN(n)) return String(value);
    if (segmentUnit === "TWD_thousands") return n.toLocaleString("en-US");
    if (segmentUnit === "USD_thousands") return `$${n.toLocaleString("en-US")}k`;
    return n.toLocaleString("en-US");
  };
  const isGrowth = growthMode !== "value";
  const gPrevFn = growthMode === "qoq" ? prevQoQ : prevYoY;

  const totalVals: Record<string, number | null> = {};
  for (const p of periods) {
    const vals = names.map((n) => segVals[n][p]).filter((v): v is number => v != null);
    totalVals[p] = vals.length ? vals.reduce((a, b) => a + b, 0) : null;
  }
  const pieEligiblePeriods = periods.filter((p) => names.every((n) => (segVals[n]?.[p] ?? 0) >= 0));

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
        <td className={`sticky left-0 z-[10] border border-[var(--border)] px-3 py-1.5 text-left font-medium whitespace-nowrap ${bgBase} ${isTotal ? "font-bold text-[#7b3f00]" : ""}`}>
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
    <section className="rounded-md bg-[var(--bg-card)] p-4 shadow-sm">
      {showTitle && <h3 className="mb-3 text-sm font-bold text-[var(--text)]">{segmentLabel(category)}</h3>}

      <div className="mb-4 rounded-md bg-[var(--bg-card)]">
        <div className="relative h-[320px]">
          <Line data={chartData} options={{
            responsive: true, maintainAspectRatio: false,
            interaction: { mode: "index" as const, intersect: false },
            plugins: {
              tooltip: { callbacks: { label: (ctx: any) => isGrowth ? `${ctx.dataset.label}: ${ctx.parsed.y?.toFixed(1)}%` : `${ctx.dataset.label}: ${formatSegmentValue(ctx.parsed.y ?? 0)}` } },
              legend: { position: "bottom" as const, labels: { boxWidth: 12, font: { size: 11 } } },
            },
            scales: {
              x: { ticks: { font: { size: 10 }, maxRotation: 45 } },
              y: { ticks: { font: { size: 10 }, callback: (v: any) => isGrowth ? `${v}%` : segmentTickLabel(v) } },
            },
          }} />
        </div>
      </div>

      {pieEligiblePeriods.length > 0 && (
        <SegmentPieChart segVals={segVals} periods={pieEligiblePeriods} formatValue={formatSegmentValue} />
      )}

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
      <div className="mt-2 text-right text-[10px] text-[var(--text-faint)]">
        Source: NotebookLM / SEC EDGAR · Unit: {segmentUnit === "TWD_thousands" ? "TWD thousands" : segmentUnit === "USD_thousands" ? "USD thousands" : "reported value"}
      </div>
    </section>
  );
}

function BusinessPnLSection({
  store,
  viewMode,
}: {
  store: FactStore;
  viewMode: "quarterly" | "annual";
}) {
  const revenue = buildSegmentCategoryVals(store, "revenue_by_business", viewMode);
  const profit = buildSegmentCategoryVals(store, "profit_by_business", viewMode);
  if (!revenue.names.length || !profit.names.length) return null;

  const periods = revenue.periods.filter((p) => profit.periods.includes(p));
  const names = revenue.names.filter((name) => profit.names.includes(name));
  if (!periods.length || !names.length) return null;

  const samplePeriod = periods[0] ?? "";
  const sampleName = names[0] ?? "";
  const unit = samplePeriod && sampleName ? store.unit("segments", "revenue_by_business", samplePeriod, sampleName) : null;

  const formatMoney = (value: number | null) => {
    if (value == null) return "—";
    if (unit === "TWD_thousands") return value.toLocaleString("en-US");
    return value.toLocaleString("en-US");
  };

  const formatMargin = (value: number | null) => {
    if (value == null) return "—";
    return `${(value * 100).toFixed(1)}%`;
  };

  return (
    <section className="rounded-md bg-[var(--bg-card)] p-4 shadow-sm">
      <h3 className="mb-3 text-sm font-bold text-[var(--text)]">Business P&amp;L</h3>
      <div className="grid gap-4 md:grid-cols-2">
        {names.map((name) => {
          const revenueVals = revenue.segVals[name];
          const profitVals = profit.segVals[name];
          const costVals: Record<string, number | null> = {};
          const marginVals: Record<string, number | null> = {};
          for (const period of periods) {
            const rev = revenueVals?.[period] ?? null;
            const prof = profitVals?.[period] ?? null;
            costVals[period] = rev != null && prof != null ? rev - prof : null;
            marginVals[period] = rev != null && rev !== 0 && prof != null ? prof / rev : null;
          }

          const rows = [
            { label: "Revenue", values: revenueVals, formatter: formatMoney },
            { label: "Cost", values: costVals, formatter: formatMoney },
            { label: "Profit", values: profitVals, formatter: formatMoney },
            { label: "Margin", values: marginVals, formatter: formatMargin },
          ];

          return (
            <div key={name} className="overflow-x-auto rounded-md border border-[var(--border)]">
              <table className="w-full border-collapse bg-[var(--bg-card)] text-xs">
                <thead>
                  <tr>
                    <th colSpan={periods.length + 1} className="border border-[var(--border)] bg-[#1f4e79] px-3 py-2 text-left font-semibold text-white">
                      {name}
                    </th>
                  </tr>
                  <tr>
                    <th className="sticky left-0 z-[11] min-w-[110px] border border-[var(--border)] bg-[#d6e4f0] px-3 py-1.5 text-left font-semibold text-[#1f4e79]">Metric</th>
                    {periods.map((period) => (
                      <th key={period} className="border border-[var(--border)] bg-[#d6e4f0] px-3 py-1.5 text-center font-semibold text-[#1f4e79] whitespace-nowrap">
                        {period}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row, idx) => {
                    const bgBase = idx % 2 === 0 ? "bg-[var(--bg-subtle)]" : "bg-[var(--bg-card)]";
                    return (
                      <tr key={row.label}>
                        <td className={`sticky left-0 z-[5] border border-[var(--border)] px-3 py-1.5 text-left font-medium ${bgBase}`}>
                          {row.label}
                        </td>
                        {periods.map((period) => {
                          const value = row.values?.[period] ?? null;
                          const negative = value != null && value < 0;
                          return (
                            <td
                              key={period}
                              className={`border border-[var(--border)] px-3 py-1.5 text-right tabular-nums ${bgBase} ${negative ? "text-[#c0392b]" : ""}`}
                            >
                              {row.formatter(value)}
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
        })}
      </div>
      <div className="mt-2 text-right text-[10px] text-[var(--text-faint)]">
        Revenue / Profit come from segment notes. Cost and Margin are derived from Revenue and Profit.
      </div>
    </section>
  );
}

function SegmentPanel({ store, viewMode }: { store: FactStore; viewMode: "quarterly" | "annual" }) {
  const categories = store.segmentCategories();
  const segOptions = categories.filter((c) => store.dimensions("segments", c).length > 0);

  const [segType, setSegType] = useState(segOptions.length > 1 ? ALL_SEGMENTS_KEY : (segOptions[0] ?? ""));
  const [growthMode, setGrowthMode] = useState<GrowthMode>("value");
  useEffect(() => { if (viewMode === "annual" && growthMode === "qoq") setGrowthMode("value"); }, [viewMode]);
  useEffect(() => {
    if (!segOptions.length) {
      setSegType("");
      return;
    }
    if (segType === ALL_SEGMENTS_KEY && segOptions.length > 1) return;
    if (!segOptions.includes(segType)) {
      setSegType(segOptions.length > 1 ? ALL_SEGMENTS_KEY : segOptions[0]);
    }
  }, [segOptions, segType]);

  if (!segOptions.length)
    return <div className="p-10 text-center text-sm text-[#7f8c8d]">No segment data available for this ticker.</div>;

  return (
    <>
      <div className="mb-3 flex items-center gap-4">
        <div className="flex gap-1">
          {segOptions.length > 1 && (
            <button key={ALL_SEGMENTS_KEY} onClick={() => setSegType(ALL_SEGMENTS_KEY)}
              className={`rounded border px-3 py-1.5 text-xs font-semibold transition-all select-none ${
                segType === ALL_SEGMENTS_KEY ? "border-[var(--primary)] bg-[var(--primary)] text-white" : "border-[var(--border)] bg-[var(--bg-subtle)] text-[var(--text-muted)] hover:border-[var(--primary)]"
              }`}
            >全部比較</button>
          )}
          {segOptions.map((key) => (
            <button key={key} onClick={() => setSegType(key)}
              className={`rounded border px-3 py-1.5 text-xs font-semibold transition-all select-none ${
                segType === key ? "border-[var(--primary)] bg-[var(--primary)] text-white" : "border-[var(--border)] bg-[var(--bg-subtle)] text-[var(--text-muted)] hover:border-[var(--primary)]"
              }`}
            >{segmentLabel(key)}</button>
          ))}
        </div>
        <GrowthToggle mode={growthMode} setMode={setGrowthMode} showQoQ={viewMode === "quarterly"} />
      </div>

      {segType === ALL_SEGMENTS_KEY ? (
        <div className="space-y-6">
          <div className="rounded-md border border-[var(--border)] bg-[var(--bg-subtle)] px-4 py-3 text-xs text-[var(--text-muted)]">
            目前以「全部比較」模式顯示所有 Segment metric，方便直接上下對照，不用逐個切換。
          </div>
          {segOptions.map((key) => (
            <SegmentCategorySection
              key={key}
              store={store}
              viewMode={viewMode}
              category={key}
              growthMode={growthMode}
            />
          ))}
          <BusinessPnLSection store={store} viewMode={viewMode} />
        </div>
      ) : (
        <div className="space-y-6">
          <SegmentCategorySection
            store={store}
            viewMode={viewMode}
            category={segType}
            growthMode={growthMode}
            showTitle={false}
          />
          <BusinessPnLSection store={store} viewMode={viewMode} />
        </div>
      )}
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
              <td className="sticky left-0 z-[10] border border-[var(--border)] bg-[var(--bg-subtle)] px-3 py-1.5 text-left font-medium">GAAP EPS (Diluted)</td>
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
              <td className="sticky left-0 z-[10] border border-[var(--border)] bg-[var(--bg-card)] px-3 py-1.5 text-left font-medium">Adjusted EPS (Non-GAAP)</td>
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
              <td className="sticky left-0 z-[10] border border-[var(--border)] bg-[var(--bg-highlight)] px-3 py-1.5 text-left font-bold text-[#7b3f00]">Δ (Non-GAAP − GAAP)</td>
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
  { id: "valuation", label: "Valuation" },
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
        {tab !== "valuation" && (
          <div className="ml-4 flex">
            {(["quarterly", "annual"] as const).map((m) => (
              <button key={m} onClick={() => setViewMode(m)}
                className={`cursor-pointer border border-white/30 px-3.5 py-1 text-xs font-semibold transition-all first:rounded-l last:rounded-r last:border-l-0 ${
                  viewMode === m ? "bg-white/20 text-white" : "text-white/70"
                }`}
              >{m === "quarterly" ? "Quarterly" : "Annual"}</button>
            ))}
          </div>
        )}
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
        {!loading && !ticker && <div className="py-16 text-center text-sm text-[#7f8c8d]">Select a ticker to view financial statements.</div>}
        {!loading && !!ticker && tab === "valuation" && (
          <ValuationChart ticker={ticker} />
        )}
        {!loading && !!ticker && tab !== "valuation" && !store && (
          <div className="py-16 text-center text-sm text-[#7f8c8d]">Financial statement data is unavailable for this ticker.</div>
        )}
        {!loading && store && tab !== "valuation" && (
          <>
            {tab === "is" && <IncomeStatement store={store} viewMode={viewMode} />}
            {tab === "bs" && <BalanceSheet store={store} viewMode={viewMode} />}
            {tab === "cf" && <CashFlowStatement store={store} viewMode={viewMode} />}
            {tab === "ratios" && <RatiosPanel store={store} viewMode={viewMode} />}
            {tab === "segments" && <SegmentPanel store={store} viewMode={viewMode} />}
            {tab === "non-gaap" && <NonGaapPanel store={store} viewMode={viewMode} />}
          </>
        )}
      </div>
    </div>
  );
}
