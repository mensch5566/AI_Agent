"use client";

import { useState, useEffect, useMemo, useCallback, useRef } from "react";
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
  TICKER_LABELS, LABEL_MAP, TOTAL_KEYS, RATIO_ORDER, RATIO_DEFINITIONS, CHART_COLORS,
  PERIOD_ORDER_WEIGHT, sortPeriods, isPct, isEps, fmtVal, labelFor,
  getIncompleteFYs,
  type ValMap, type FinData,
} from "@/app/components/financials/constants";
import { toAnnualData } from "@/app/components/financials/useFinancialData";

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
  Legend,
);

function getPeriodEnd(data: FinData, period: string) {
  return data.filings?.[period]?.period_end ?? "";
}

/* ================================================================
   Growth rate helpers (QoQ / YoY)
   ================================================================ */
type GrowthMode = "value" | "qoq" | "yoy";

/** Parse "Q2_FY2025" → { q: 2, fy: 2025 } or "FY2025" → { q: 0, fy: 2025 } */
function parsePeriod(p: string): { q: number; fy: number } | null {
  const qm = p.match(/^Q(\d)_FY(\d{4})$/);
  if (qm) return { q: Number(qm[1]), fy: Number(qm[2]) };
  const fm = p.match(/^FY(\d{4})$/);
  if (fm) return { q: 0, fy: Number(fm[1]) };
  return null;
}

/** Get the previous period key for QoQ (previous quarter) */
function prevQoQ(p: string): string | null {
  const pp = parsePeriod(p);
  if (!pp || pp.q === 0) return null; // annual → no QoQ
  if (pp.q === 1) return `Q4_FY${pp.fy - 1}`;
  return `Q${pp.q - 1}_FY${pp.fy}`;
}

/** Get the same-quarter-last-year key for YoY */
function prevYoY(p: string): string | null {
  const pp = parsePeriod(p);
  if (!pp) return null;
  if (pp.q === 0) return `FY${pp.fy - 1}`;
  return `Q${pp.q}_FY${pp.fy - 1}`;
}

/** Compute growth % between two values. Returns null if either is missing or prev is 0. */
function growthPct(curr: number | null | undefined, prev: number | null | undefined): number | null {
  if (curr == null || prev == null || prev === 0) return null;
  return (curr - prev) / Math.abs(prev);
}

/** Format growth as percentage string */
function fmtGrowth(pct: number | null): { text: string; cls: string } {
  if (pct === null) return { text: "—", cls: "null-val" };
  const text = (pct >= 0 ? "+" : "") + (pct * 100).toFixed(1) + "%";
  return { text, cls: pct < 0 ? "negative" : pct > 0 ? "positive" : "" };
}

/** Reusable toggle for Value / QoQ / YoY */
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

/* ================================================================
   Row types for table rendering
   ================================================================ */
type TableRow =
  | { type: "section"; label: string }
  | { type: "data"; key: string; label: string; vals: ValMap };

function buildRows(metrics: Record<string, ValMap>): TableRow[] {
  return Object.entries(metrics).map(([key, vals]) => ({
    type: "data" as const,
    key,
    label: labelFor(key),
    vals,
  }));
}

/* ================================================================
   Sub-components
   ================================================================ */

/* ── Generic data table ── */
function DataTable({
  periods,
  rows,
  data,
  growthMode = "value",
  incompleteFYs = new Map(),
}: {
  periods: string[];
  rows: TableRow[];
  data: FinData;
  growthMode?: GrowthMode;
  incompleteFYs?: Map<string, number>;
}) {
  if (!rows.length) return <div className="p-10 text-center text-sm text-[#7f8c8d]">No data available.</div>;

  const isGrowth = growthMode !== "value";
  const prevFn = growthMode === "qoq" ? prevQoQ : prevYoY;
  const hasIncomplete = incompleteFYs.size > 0;

  return (
    <>
      <div className="overflow-x-auto rounded-md shadow-sm">
        <table className="w-full border-collapse bg-[var(--bg-card)] text-xs">
          <thead>
            <tr>
              <th className="sticky left-0 z-[11] min-w-[260px] border border-[var(--border)] bg-[#1f4e79] px-3 py-1.5 text-left font-semibold text-white">
                Metric
              </th>
              {periods.map((p) => {
                const end = getPeriodEnd(data, p);
                const qCount = incompleteFYs.get(p);
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
              const bgBase = isTotal
                ? "bg-[var(--bg-highlight)]"
                : i % 2 === 0
                  ? "bg-[var(--bg-subtle)]"
                  : "bg-[var(--bg-card)]";
              const textCls = isTotal ? "font-bold text-[#7b3f00]" : "";
              // Skip growth for percentage/ratio rows — growth of a margin % is misleading
              const skipGrowth = isGrowth && (isPct(row.key) || row.key.includes("ratio") || row.key === "debt_to_equity" || row.key === "net_debt_to_equity");
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
                      const isPartial = incompleteFYs.has(p) || (prevKey ? incompleteFYs.has(prevKey) : false);
                      return (
                        <td
                          key={p}
                          title={isPartial ? "數據未完整，僅部分季度" : undefined}
                          className={`border border-[var(--border)] px-3 py-1.5 tabular-nums ${bgBase} ${
                            f.cls === "negative"
                              ? "text-right text-[#c0392b]"
                              : f.cls === "positive"
                                ? "text-right text-[#27ae60]"
                                : f.cls === "null-val"
                                  ? "text-center text-[#7f8c8d]"
                                  : "text-right"
                          }`}
                        >
                          {f.text}{isPartial && f.cls !== "null-val" && <span className="ml-0.5 text-[9px] text-amber-500">*</span>}
                        </td>
                      );
                    }
                    const v = row.vals?.[p];
                    const f = fmtVal(v, row.key, data.metadata?.currency);
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
      {hasIncomplete && (
        <div className="mt-1.5 text-right text-[10px] text-amber-600">
          * 數據未完整（僅部分季度），YoY 比較可能失真
        </div>
      )}
    </>
  );
}

/* ── Income Statement ── */
const IS_CHART_METRICS = [
  { key: "revenue", label: "Revenue" },
  { key: "gross_profit", label: "Gross Profit" },
  { key: "operating_income", label: "Operating Income" },
  { key: "net_income", label: "Net Income" },
];

function IncomeStatement({ data, viewMode }: { data: FinData; viewMode: "quarterly" | "annual" }) {
  const [growthMode, setGrowthMode] = useState<GrowthMode>("value");
  // Reset QoQ to Value when switching to Annual
  useEffect(() => { if (viewMode === "annual" && growthMode === "qoq") setGrowthMode("value"); }, [viewMode]);
  const periods = sortPeriods(data.metadata.periods_income_statement || []);
  const rows = buildRows(data.income_statement || {});
  const is = data.income_statement || {};
  // Incomplete FYs from toAnnualData metadata (only present in annual mode)
  const incompleteFYs = useMemo(() => {
    if (viewMode !== "annual") return new Map<string, number>();
    const raw = data.metadata?.incomplete_fys;
    return raw ? new Map(Object.entries(raw).map(([k, v]) => [k, v as number])) : new Map<string, number>();
  }, [data, viewMode]);

  const isGrowth = growthMode !== "value";
  const prevFn = growthMode === "qoq" ? prevQoQ : prevYoY;

  const chartData = {
    labels: periods,
    datasets: IS_CHART_METRICS
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
  };

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: "index" as const, intersect: false },
    plugins: {
      tooltip: {
        callbacks: {
          label: (ctx: any) => isGrowth ? `${ctx.dataset.label}: ${ctx.parsed.y?.toFixed(1)}%` : `${ctx.dataset.label}: $${ctx.parsed.y?.toLocaleString()}M`,
        },
      },
      legend: { position: "bottom" as const, labels: { boxWidth: 12, font: { size: 11 } } },
    },
    scales: {
      x: { ticks: { font: { size: 10 }, maxRotation: 45 } },
      y: { ticks: { font: { size: 10 }, callback: (v: any) => isGrowth ? `${v}%` : `$${v}M` } },
    },
  };

  return (
    <>
      <div className="mb-3">
        <GrowthToggle mode={growthMode} setMode={setGrowthMode} showQoQ={viewMode === "quarterly"} />
      </div>

      {/* Chart */}
      <div className="mb-4 rounded-md bg-[var(--bg-card)] p-4 shadow-sm">
        <div className="relative h-[320px]">
          <Line data={chartData} options={chartOptions} />
        </div>
      </div>

      <DataTable periods={periods} rows={rows} data={data} growthMode={growthMode} incompleteFYs={incompleteFYs} />
    </>
  );
}

/* ── Balance Sheet ── */
function BalanceSheet({ data }: { data: FinData }) {
  const periods = sortPeriods(data.metadata.periods_balance_sheet || []);
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
  return <DataTable periods={periods} rows={rows} data={data} />;
}

/* ── Cash Flow ── */
function CashFlowStatement({ data }: { data: FinData }) {
  const periods = sortPeriods(data.metadata.periods_income_statement || []);
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
  return <DataTable periods={periods} rows={rows} data={data} />;
}

/* ── Ratios Panel (chart + table) ── */
function RatiosPanel({ data }: { data: FinData }) {
  const ratios = data.financial_ratios;
  const [selected, setSelected] = useState<Set<string>>(
    () => new Set(["gross_margin_pct", "operating_margin_pct", "net_margin_pct"]),
  );

  if (!ratios || !Object.keys(ratios).length)
    return <div className="p-10 text-center text-sm text-[#7f8c8d]">No financial ratios computed.</div>;

  const periods = sortPeriods(Object.keys(ratios));
  const metricKeys = new Set<string>();
  for (const p of periods) for (const k of Object.keys(ratios[p])) metricKeys.add(k);
  const ordered = RATIO_ORDER.filter((k) => metricKeys.has(k));
  for (const k of metricKeys) if (!ordered.includes(k)) ordered.push(k);

  const toggleMetric = (m: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(m)) next.delete(m);
      else next.add(m);
      return next;
    });
  };

  const selArr = ordered.filter((k) => selected.has(k));
  const usePercent = selArr.some(
    (k) => k.includes("pct") || k === "roe" || k === "roa" || k === "equity_ratio" || k === "asset_turnover",
  );

  const chartData = {
    labels: periods,
    datasets: selArr.map((key, i) => ({
      label: labelFor(key),
      data: periods.map((p) => ratios[p]?.[key] ?? null),
      borderColor: CHART_COLORS[i % CHART_COLORS.length],
      backgroundColor: CHART_COLORS[i % CHART_COLORS.length] + "22",
      tension: 0.3,
      pointRadius: 3,
      spanGaps: true,
    })),
  };

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: "index" as const, intersect: false },
    plugins: {
      tooltip: {
        callbacks: {
          label: (ctx: any) => {
            const key = selArr[ctx.datasetIndex];
            const v = ctx.parsed.y;
            if (v === null) return `${ctx.dataset.label}: —`;
            if (isPct(key)) return `${ctx.dataset.label}: ${(v * 100).toFixed(1)}%`;
            return `${ctx.dataset.label}: ${v.toFixed(2)}`;
          },
        },
      },
      legend: { position: "bottom" as const, labels: { boxWidth: 12, font: { size: 11 } } },
    },
    scales: {
      x: { ticks: { font: { size: 10 }, maxRotation: 45 } },
      y: {
        ticks: {
          font: { size: 10 },
          callback: (v: any) => (usePercent ? (v * 100).toFixed(0) + "%" : Number(v).toFixed(2)),
        },
      },
    },
  };

  return (
    <>
      {/* Chart */}
      <div className="mb-4 rounded-md bg-[var(--bg-card)] p-4 shadow-sm">
        <div className="mb-3 flex flex-wrap items-center gap-1.5">
          {ordered.map((key) => (
            <button
              key={key}
              onClick={() => toggleMetric(key)}
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
          {selArr.length > 0 && <Line data={chartData} options={chartOptions} />}
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-md shadow-sm">
        <table className="w-full border-collapse bg-[var(--bg-card)] text-xs">
          <thead>
            <tr>
              <th className="sticky left-0 z-[11] min-w-[260px] border border-[var(--border)] bg-[#1f4e79] px-3 py-1.5 text-left font-semibold text-white">
                Metric
              </th>
              {periods.map((p) => {
                const end = getPeriodEnd(data, p);
                return (
                  <th key={p} className="border border-[var(--border)] bg-[#1f4e79] px-3 py-1.5 text-center font-semibold text-white">
                    {p}
                    {end && <span className="block text-[10px] font-normal text-white/70">{end}</span>}
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
                    {def && (
                      <span className="pointer-events-none absolute left-full top-1/2 z-50 ml-2 hidden -translate-y-1/2 whitespace-nowrap rounded bg-[#2c3e50] px-2.5 py-1.5 text-[11px] font-normal text-white shadow-lg group-hover:block">
                        {def}
                      </span>
                    )}
                  </td>
                  {periods.map((p) => {
                    const v = (data.financial_ratios[p] as any)?.[key] ?? null;
                    const f = fmtVal(v, key, data.metadata?.currency);
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
    </>
  );
}

/* ── Tag Audit ── */
const IS_METRICS = new Set([
  "revenue", "cost_of_goods_sold", "gross_profit", "research_and_development",
  "selling_general_administrative", "restructuring_charges", "operating_income",
  "interest_expense", "interest_income", "other_nonoperating_income_expense",
  "income_before_taxes", "income_tax_expense", "equity_method_investments",
  "net_income", "eps_basic", "eps_diluted", "shares_basic", "shares_diluted",
]);
const BS_METRICS = new Set([
  "cash_and_cash_equivalents", "short_term_investments", "accounts_receivable",
  "inventories", "other_current_assets", "total_current_assets",
  "property_plant_equipment_net", "operating_lease_rou_asset", "goodwill",
  "intangible_assets", "deferred_tax_assets", "other_noncurrent_assets",
  "total_assets", "accounts_payable", "accrued_liabilities", "current_debt",
  "other_current_liabilities", "total_current_liabilities", "long_term_debt",
  "operating_lease_noncurrent", "other_noncurrent_liabilities",
  "total_liabilities", "common_stock", "additional_paid_in_capital",
  "retained_earnings", "treasury_stock", "aoci", "total_equity",
  "total_liabilities_and_equity",
]);

function TagAuditPanel({ data }: { data: FinData }) {
  const audit = data.classification_audit || data.tag_history || {};
  if (!Object.keys(audit).length)
    return <div className="p-10 text-center text-sm text-[#7f8c8d]">No tag audit data available.</div>;

  const isNew = !!data.classification_audit;
  const groups: Record<string, { metric: string; info: any }[]> = {
    "Income Statement": [],
    "Balance Sheet": [],
    "Cash Flow": [],
  };
  for (const [metric, info] of Object.entries(audit)) {
    const bucket = IS_METRICS.has(metric) ? "Income Statement" : BS_METRICS.has(metric) ? "Balance Sheet" : "Cash Flow";
    groups[bucket].push({ metric, info });
  }

  const BADGE: Record<string, { cls: string; text: string }> = {
    known: { cls: "bg-[#27ae60]", text: "K" },
    label_discovery: { cls: "bg-[#2980b9]", text: "L" },
    llm_inference: { cls: "bg-[#8e44ad]", text: "AI" },
  };

  return (
    <div>
      {/* Legend */}
      <div className="mb-3 flex gap-4 border-b border-[var(--border)] pb-3 text-xs text-[#7f8c8d]">
        {Object.entries(BADGE).map(([method, b]) => (
          <div key={method} className="flex items-center gap-1">
            <span className={`inline-block rounded-full px-2 py-0.5 text-[10px] font-bold text-white ${b.cls}`}>{b.text}</span>
            {method === "known" ? "Known candidate" : method === "label_discovery" ? "Label discovery" : "LLM inference"}
          </div>
        ))}
      </div>

      {Object.entries(groups).map(([section, items]) => {
        if (!items.length) return null;
        return (
          <div key={section}>
            <div className="my-4 rounded bg-[#d6e4f0] px-4 py-2 text-[13px] font-bold uppercase tracking-wide text-[#1f4e79]">
              {section}
            </div>
            {items.map(({ metric, info }) => {
              const tags = isNew
                ? (info.tags || [])
                : ((info as any).tags_used || []).map((tag: string) => ({
                    tag,
                    label: tag,
                    method: "known",
                    confidence: 1.0,
                    periods: Object.entries((info as any).tag_by_period || {})
                      .filter(([, t]) => t === tag)
                      .map(([p]) => p),
                  }));
              const hasLLM = tags.some((t: any) => t.method === "llm_inference");
              return (
                <div
                  key={metric}
                  className={`mb-3 rounded-md border-l-4 bg-[var(--bg-card)] p-4 shadow-sm ${
                    tags.length > 1 ? "border-l-[#e67e22]" : hasLLM ? "border-l-[#8e44ad]" : "border-l-[#1f4e79]"
                  }`}
                >
                  <div className="mb-2 text-sm font-bold text-[#1f4e79]">
                    {labelFor(metric)} <span className="font-normal text-[#7f8c8d]">({metric})</span>
                  </div>
                  {tags.map((t: any, ti: number) => {
                    const badge = BADGE[t.method] || BADGE.known;
                    const periods = sortPeriods(t.periods || []);
                    return (
                      <div key={ti} className="mb-1.5 flex items-start gap-2 rounded bg-[var(--bg-subtle)] px-3 py-2 text-xs last:mb-0">
                        <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-bold text-white ${badge.cls}`}>
                          {badge.text}
                        </span>
                        <div>
                          <div className="font-medium">{t.label || t.tag}</div>
                          <div className="font-mono text-[11px] text-[#555] break-all">{t.tag}</div>
                          {periods.length > 0 && (
                            <div className="mt-1 text-[11px] text-[#7f8c8d]">
                              {periods.length} periods: {periods[0]} → {periods[periods.length - 1]}
                            </div>
                          )}
                          {t.confidence < 1.0 && (
                            <div className="text-[11px] text-[#7f8c8d]">
                              Confidence: {(t.confidence * 100).toFixed(0)}%
                            </div>
                          )}
                          {t.reasoning && (
                            <div className="mt-1 text-[11px] italic text-[#8e44ad]">&ldquo;{t.reasoning}&rdquo;</div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              );
            })}
          </div>
        );
      })}
    </div>
  );
}

/* ── Segment Panel ── */
function aggregateSegmentsAnnual(segments: Record<string, Record<string, { value: number; source: string }>>): Record<string, Record<string, { value: number; source: string }>> {
  const annual: Record<string, Record<string, { value: number; source: string }>> = {};
  for (const [period, segs] of Object.entries(segments)) {
    const match = period.match(/Q\d_FY(\d+)/);
    if (!match) continue;
    const fy = `FY${match[1]}`;
    if (!annual[fy]) annual[fy] = {};
    for (const [name, entry] of Object.entries(segs)) {
      if (!annual[fy][name]) {
        annual[fy][name] = { value: 0, source: entry.source };
      }
      annual[fy][name].value += entry.value;
    }
  }
  return annual;
}

function SegmentPanel({ suppData, viewMode }: { suppData: any; viewMode: "quarterly" | "annual" }) {
  const segOptions: [string, string][] = [
    ["revenue_by_business", "By Business"],
    ["revenue_by_product", "By Product"],
    ["revenue_by_geography", "By Geography"],
  ].filter(([key]) => suppData?.segments?.[key] && Object.keys(suppData.segments[key]).length > 0) as [string, string][];

  const [segType, setSegType] = useState(segOptions[0]?.[0] ?? "revenue_by_product");
  const [growthMode, setGrowthMode] = useState<GrowthMode>("value");
  // Reset QoQ to Value when switching to Annual
  useEffect(() => { if (viewMode === "annual" && growthMode === "qoq") setGrowthMode("value"); }, [viewMode]);

  if (!suppData?.segments || segOptions.length === 0)
    return <div className="p-10 text-center text-sm text-[#7f8c8d]">No segment data available for this ticker.</div>;

  const rawSegments = suppData.segments[segType];
  if (!rawSegments || !Object.keys(rawSegments).length)
    return <div className="p-10 text-center text-sm text-[#7f8c8d]">No segment data for this view.</div>;

  const segments = viewMode === "annual" ? aggregateSegmentsAnnual(rawSegments) : rawSegments;
  const periods = sortPeriods(Object.keys(segments));
  // Detect incomplete FYs for segment data
  const segIncompleteFYs = useMemo(() => {
    if (viewMode !== "annual") return new Map<string, number>();
    const qPeriods = Object.keys(rawSegments).filter((p) => /^Q\d_FY\d{4}$/.test(p));
    return getIncompleteFYs(qPeriods);
  }, [rawSegments, viewMode]);
  const hasIncomplete = viewMode === "annual" && segIncompleteFYs.size > 0;
  // Collect all segment names across periods
  const segNames = new Set<string>();
  for (const p of periods) for (const name of Object.keys(segments[p])) segNames.add(name);
  const names = Array.from(segNames);

  const isGrowth = growthMode !== "value";
  const gPrevFn = growthMode === "qoq" ? prevQoQ : prevYoY;

  // Chart data: line chart
  const chartData = {
    labels: periods,
    datasets: names.map((name, i) => ({
      label: name,
      data: isGrowth
        ? periods.map((p) => { const pk = gPrevFn(p); const g = growthPct(segments[p]?.[name]?.value, pk ? segments[pk]?.[name]?.value : null); return g != null ? +(g * 100).toFixed(1) : null; })
        : periods.map((p) => segments[p]?.[name]?.value ?? 0),
      borderColor: CHART_COLORS[i % CHART_COLORS.length],
      backgroundColor: CHART_COLORS[i % CHART_COLORS.length] + "cc",
      tension: 0.3,
      pointRadius: 3,
    })),
  };

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: "index" as const, intersect: false },
    plugins: {
      tooltip: {
        callbacks: {
          label: (ctx: any) => isGrowth ? `${ctx.dataset.label}: ${ctx.parsed.y?.toFixed(1)}%` : `${ctx.dataset.label}: $${ctx.parsed.y}M`,
        },
      },
      legend: { position: "bottom" as const, labels: { boxWidth: 12, font: { size: 11 } } },
    },
    scales: {
      x: { ticks: { font: { size: 10 }, maxRotation: 45 } },
      y: {
        ticks: {
          font: { size: 10 },
          callback: (v: any) => isGrowth ? `${v}%` : `$${v}M`,
        },
      },
    },
  };

  return (
    <>
      {/* Segment type toggle + Growth toggle */}
      <div className="mb-3 flex items-center gap-4">
        <div className="flex gap-1">
          {segOptions.map(([key, label]) => (
            <button
              key={key}
              onClick={() => setSegType(key)}
              className={`rounded border px-3 py-1.5 text-xs font-semibold transition-all select-none ${
                segType === key
                  ? "border-[var(--primary)] bg-[var(--primary)] text-white"
                  : "border-[var(--border)] bg-[var(--bg-subtle)] text-[var(--text-muted)] hover:border-[var(--primary)]"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
        <GrowthToggle mode={growthMode} setMode={setGrowthMode} showQoQ={viewMode === "quarterly"} />
      </div>

      {/* Line Chart */}
      <div className="mb-4 rounded-md bg-[var(--bg-card)] p-4 shadow-sm">
        <div className="relative h-[320px]">
          <Line data={chartData} options={chartOptions} />
        </div>
      </div>

      {/* Pie Chart */}
      {(() => {
        const segVals: Record<string, Record<string, number | null>> = {};
        for (const name of names) {
          segVals[name] = {};
          for (const p of periods) {
            segVals[name][p] = segments[p]?.[name]?.value ?? null;
          }
        }
        return <SegmentPieChart segVals={segVals} periods={periods} />;
      })()}

      {/* Table */}
      <div className="overflow-x-auto rounded-md shadow-sm">
        <table className="w-full border-collapse bg-[var(--bg-card)] text-xs">
          <thead>
            <tr>
              <th className="sticky left-0 z-[11] min-w-[180px] border border-[var(--border)] bg-[#1f4e79] px-3 py-1.5 text-left font-semibold text-white">
                Segment
              </th>
              {periods.map((p) => {
                const qCount = segIncompleteFYs.get(p);
                return (
                  <th key={p} className="border border-[var(--border)] bg-[#1f4e79] px-3 py-1.5 text-center font-semibold text-white whitespace-nowrap">
                    {p}
                    {qCount && <span className="ml-1 inline-block rounded bg-amber-500/80 px-1 py-px text-[9px] font-normal leading-tight text-white" title={`僅 ${qCount} 季數據`}>{qCount}Q</span>}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {names.map((name, i) => {
              const isGrowth = growthMode !== "value";
              const gPrevFn = growthMode === "qoq" ? prevQoQ : prevYoY;
              const bgBase = i % 2 === 0 ? "bg-[var(--bg-subtle)]" : "bg-[var(--bg-card)]";
              return (
                <tr key={name}>
                  <td className={`sticky left-0 z-[5] border border-[var(--border)] px-3 py-1.5 text-left font-medium ${bgBase}`}>
                    {name}
                  </td>
                  {periods.map((p) => {
                    const entry = segments[p]?.[name];
                    const val = entry?.value ?? null;
                    if (isGrowth) {
                      const prevKey = gPrevFn(p);
                      const prevVal = prevKey ? (segments[prevKey]?.[name]?.value ?? null) : null;
                      const g = growthPct(val, prevVal);
                      const f = fmtGrowth(g);
                      const isPartial = segIncompleteFYs.has(p) || (prevKey ? segIncompleteFYs.has(prevKey) : false);
                      return (
                        <td
                          key={p}
                          title={isPartial ? "數據未完整，僅部分季度" : entry?.source || ""}
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
                    return (
                      <td
                        key={p}
                        title={entry?.source || ""}
                        className={`border border-[var(--border)] px-3 py-1.5 text-right tabular-nums ${bgBase}`}
                      >
                        {val != null ? `$${val.toLocaleString()}M` : "—"}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
            {/* Total row */}
            <tr>
              <td className="sticky left-0 z-[5] border border-[var(--border)] bg-[var(--bg-highlight)] px-3 py-1.5 text-left font-bold text-[#7b3f00]">
                Total
              </td>
              {periods.map((p) => {
                const total = names.reduce((sum, name) => sum + (segments[p]?.[name]?.value ?? 0), 0);
                if (growthMode !== "value") {
                  const gPrevFn = growthMode === "qoq" ? prevQoQ : prevYoY;
                  const prevKey = gPrevFn(p);
                  const prevTotal = prevKey ? names.reduce((sum, name) => sum + (segments[prevKey]?.[name]?.value ?? 0), 0) : null;
                  const g = growthPct(total, prevTotal);
                  const f = fmtGrowth(g);
                  const isPartial = segIncompleteFYs.has(p) || (prevKey ? segIncompleteFYs.has(prevKey) : false);
                  return (
                    <td key={p} title={isPartial ? "數據未完整，僅部分季度" : undefined} className={`border border-[var(--border)] bg-[var(--bg-highlight)] px-3 py-1.5 text-right font-bold tabular-nums ${
                      f.cls === "negative" ? "text-[#c0392b]" : f.cls === "positive" ? "text-[#27ae60]" : "text-[#7b3f00]"
                    }`}>
                      {f.text}{isPartial && f.cls !== "null-val" && <span className="ml-0.5 text-[9px] text-amber-500">*</span>}
                    </td>
                  );
                }
                return (
                  <td key={p} className="border border-[var(--border)] bg-[var(--bg-highlight)] px-3 py-1.5 text-right font-bold tabular-nums text-[#7b3f00]">
                    ${total.toLocaleString()}M
                  </td>
                );
              })}
            </tr>
          </tbody>
        </table>
      </div>

      {/* Source footnote */}
      <div className="mt-2 flex justify-between text-[10px]">
        {hasIncomplete && <span className="text-amber-600">* 數據未完整（僅部分季度），YoY 比較可能失真</span>}
        <span className="ml-auto text-[var(--text-faint)]">Source: NotebookLM / SEC EDGAR · hover over cells for detailed source</span>
      </div>
    </>
  );
}

/* ── Non-GAAP Panel ── */
function NonGaapPanel({ suppData, gaapData, viewMode }: { suppData: any; gaapData: FinData; viewMode: "quarterly" | "annual" }) {
  if (!suppData?.non_gaap || !Object.keys(suppData.non_gaap).length)
    return <div className="p-10 text-center text-sm text-[#7f8c8d]">No Non-GAAP data available for this ticker.</div>;

  const nonGaap = suppData.non_gaap;

  // Adjusted EPS section
  const adjEps = nonGaap.adjusted_eps_diluted;
  if (!adjEps || !Object.keys(adjEps).length)
    return <div className="p-10 text-center text-sm text-[#7f8c8d]">No adjusted EPS data available.</div>;

  const allPeriods = sortPeriods(Object.keys(adjEps));
  const quarterlyPeriods = allPeriods.filter((p) => p.startsWith("Q"));
  const annualPeriods = allPeriods.filter((p) => p.startsWith("FY"));

  // Get GAAP EPS for comparison
  const gaapEps = gaapData?.income_statement?.eps_diluted || {};

  return (
    <div>
      <h3 className="mb-3 text-sm font-bold text-[var(--text)]">Adjusted EPS (Diluted) — GAAP vs Non-GAAP</h3>

      {/* Quarterly comparison table */}
      {quarterlyPeriods.length > 0 && (
        <>
          <div className="mb-2 text-xs font-semibold text-[var(--text-muted)]">Quarterly</div>
          <div className="mb-4 overflow-x-auto rounded-md shadow-sm">
            <table className="w-full border-collapse bg-[var(--bg-card)] text-xs">
              <thead>
                <tr>
                  <th className="sticky left-0 z-[11] min-w-[200px] border border-[var(--border)] bg-[#1f4e79] px-3 py-1.5 text-left font-semibold text-white">
                    Metric
                  </th>
                  {quarterlyPeriods.map((p) => (
                    <th key={p} className="border border-[var(--border)] bg-[#1f4e79] px-3 py-1.5 text-center font-semibold text-white whitespace-nowrap">
                      {p}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {/* GAAP EPS row */}
                <tr>
                  <td className="sticky left-0 z-[5] border border-[var(--border)] bg-[var(--bg-subtle)] px-3 py-1.5 text-left font-medium">
                    GAAP EPS (Diluted)
                  </td>
                  {quarterlyPeriods.map((p) => {
                    const v = gaapEps[p];
                    return (
                      <td key={p} className={`border border-[var(--border)] bg-[var(--bg-subtle)] px-3 py-1.5 text-right tabular-nums ${
                        v != null && v < 0 ? "text-[#c0392b]" : ""
                      }`}>
                        {v != null ? `$${Number(v).toFixed(2)}` : "—"}
                      </td>
                    );
                  })}
                </tr>
                {/* Non-GAAP EPS row */}
                <tr>
                  <td className="sticky left-0 z-[5] border border-[var(--border)] bg-[var(--bg-card)] px-3 py-1.5 text-left font-medium">
                    Adjusted EPS (Non-GAAP)
                  </td>
                  {quarterlyPeriods.map((p) => {
                    const entry = adjEps[p];
                    const v = entry?.value;
                    return (
                      <td
                        key={p}
                        title={entry?.source || ""}
                        className={`border border-[var(--border)] bg-[var(--bg-card)] px-3 py-1.5 text-right tabular-nums ${
                          v != null && v < 0 ? "text-[#c0392b]" : ""
                        }`}
                      >
                        {v != null ? `$${Number(v).toFixed(2)}` : "—"}
                      </td>
                    );
                  })}
                </tr>
                {/* Delta row */}
                <tr>
                  <td className="sticky left-0 z-[5] border border-[var(--border)] bg-[var(--bg-highlight)] px-3 py-1.5 text-left font-bold text-[#7b3f00]">
                    Δ (Non-GAAP − GAAP)
                  </td>
                  {quarterlyPeriods.map((p) => {
                    const gaap = gaapEps[p];
                    const nonGaapV = adjEps[p]?.value;
                    const delta = gaap != null && nonGaapV != null ? nonGaapV - Number(gaap) : null;
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
      )}

      {/* Annual summary */}
      {annualPeriods.length > 0 && (
        <>
          <div className="mb-2 text-xs font-semibold text-[var(--text-muted)]">Annual</div>
          <div className="mb-4 overflow-x-auto rounded-md shadow-sm">
            <table className="w-full border-collapse bg-[var(--bg-card)] text-xs">
              <thead>
                <tr>
                  <th className="sticky left-0 z-[11] min-w-[200px] border border-[var(--border)] bg-[#1f4e79] px-3 py-1.5 text-left font-semibold text-white">
                    Metric
                  </th>
                  {annualPeriods.map((p) => (
                    <th key={p} className="border border-[var(--border)] bg-[#1f4e79] px-3 py-1.5 text-center font-semibold text-white whitespace-nowrap">
                      {p}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td className="sticky left-0 z-[5] border border-[var(--border)] bg-[var(--bg-card)] px-3 py-1.5 text-left font-medium">
                    Adjusted EPS (Non-GAAP)
                  </td>
                  {annualPeriods.map((p) => {
                    const entry = adjEps[p];
                    const v = entry?.value;
                    return (
                      <td
                        key={p}
                        title={entry?.source || ""}
                        className={`border border-[var(--border)] bg-[var(--bg-card)] px-3 py-1.5 text-right tabular-nums ${
                          v != null && v < 0 ? "text-[#c0392b]" : ""
                        }`}
                      >
                        {v != null ? `$${Number(v).toFixed(2)}` : "—"}
                      </td>
                    );
                  })}
                </tr>
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* Source footnote */}
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
  { id: "audit", label: "Tag Audit" },
];

export default function Viewer() {
  const [tickers, setTickers] = useState<string[]>([]);
  const [ticker, setTicker] = useState("");
  const [tab, setTab] = useState("is");
  const [viewMode, setViewMode] = useState<"quarterly" | "annual">("quarterly");
  const [rawData, setRawData] = useState<FinData | null>(null);
  const [suppData, setSuppData] = useState<any | null>(null);
  const [loading, setLoading] = useState(false);

  // Load ticker list
  useEffect(() => {
    fetch("/data/financials/tickers.json")
      .then((r) => r.json())
      .then(setTickers)
      .catch(() => setTickers(["SNDK", "MU", "LEU"]));
  }, []);

  // Load financials + supplemental on ticker change
  useEffect(() => {
    if (!ticker) {
      setRawData(null);
      setSuppData(null);
      return;
    }
    setLoading(true);
    setSuppData(null);

    fetch(`/data/financials/${ticker}/${ticker}_financials.json`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((d) => {
        setRawData(d);
        setLoading(false);
      })
      .catch((e) => {
        setRawData(null);
        setLoading(false);
        alert(`Failed to load ${ticker}: ${e.message}`);
      });

    // Supplemental is optional — silently ignore if missing
    fetch(`/data/financials/${ticker}/${ticker}_supplemental.json`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => setSuppData(d))
      .catch(() => setSuppData(null));
  }, [ticker]);

  const displayData = useMemo(() => {
    if (!rawData) return null;
    return viewMode === "annual" ? toAnnualData(rawData) : rawData;
  }, [rawData, viewMode]);

  const meta = rawData?.metadata;

  return (
    <div className="min-h-screen bg-[var(--bg-page)]">
      {/* ── Top Bar ── */}
      <div className="sticky top-0 z-50 flex items-center gap-4 bg-[#1f4e79] px-6 py-3 text-white shadow-md">
        <Link
          href="/"
          className="text-sm text-white opacity-70 transition-opacity hover:opacity-100"
        >
          ← Portal
        </Link>
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

        {/* View toggle */}
        <div className="ml-4 flex">
          {(["quarterly", "annual"] as const).map((m) => (
            <button
              key={m}
              onClick={() => setViewMode(m)}
              className={`cursor-pointer border border-white/30 px-3.5 py-1 text-xs font-semibold transition-all first:rounded-l last:rounded-r last:border-l-0 ${
                viewMode === m ? "bg-white/20 text-white" : "text-white/70"
              }`}
            >
              {m === "quarterly" ? "Quarterly" : "Annual"}
            </button>
          ))}
        </div>

        <ThemeToggle />

        {meta && (
          <div className="ml-auto text-xs text-white/70">
            {meta.company}{meta.exchange ? ` | ${meta.exchange}` : ""} | {meta.currency || "USD"} {meta.unit === "millions_except_per_share" ? "millions" : meta.unit || ""} | Updated: {meta.last_updated}
          </div>
        )}
      </div>

      {/* ── Tab Bar ── */}
      <div className="sticky top-[48px] z-40 flex gap-0 border-b-2 border-[var(--border)] bg-[var(--bg-card)] px-6">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`-mb-0.5 cursor-pointer border-b-2 px-5 py-2.5 text-[13px] font-medium transition-all select-none ${
              tab === t.id
                ? "border-[#1f4e79] font-bold text-[#1f4e79]"
                : "border-transparent text-[#7f8c8d] hover:text-[#2a6da8]"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* ── Content ── */}
      <div className="mx-auto max-w-full overflow-x-auto p-4 px-6">
        {loading && <div className="py-16 text-center text-sm text-[#7f8c8d]">Loading...</div>}
        {!loading && !displayData && (
          <div className="py-16 text-center text-sm text-[#7f8c8d]">Select a ticker to view financial statements.</div>
        )}
        {!loading && displayData && (
          <>
            {tab === "is" && <IncomeStatement data={displayData} viewMode={viewMode} />}
            {tab === "bs" && <BalanceSheet data={displayData} />}
            {tab === "cf" && <CashFlowStatement data={displayData} />}
            {tab === "ratios" && <RatiosPanel data={displayData} />}
            {tab === "segments" && <SegmentPanel suppData={suppData} viewMode={viewMode} />}
            {tab === "non-gaap" && <NonGaapPanel suppData={suppData} gaapData={displayData} viewMode={viewMode} />}
            {tab === "audit" && <TagAuditPanel data={displayData} />}
          </>
        )}
      </div>
    </div>
  );
}
