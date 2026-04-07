"use client";

import { useState, useEffect, useMemo } from "react";
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
import SegmentPieChart from "./SegmentPieChart";
import {
  sortPeriods, fmtVal, PERIOD_ORDER_WEIGHT, CHART_COLORS,
  type GrowthMode, prevQoQ, prevYoY, growthPct, fmtGrowth,
  getIncompleteFYs,
} from "./constants";
import { useFinancialData } from "./useFinancialData";

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Legend);

/* ================================================================
   Types
   ================================================================ */
interface SegmentEntry {
  value: number;
  source?: string;
}

type SegmentPeriodData = Record<string, SegmentEntry>;
type SegmentCategory = Record<string, SegmentPeriodData>;

/* ================================================================
   Helpers
   ================================================================ */
const CATEGORY_LABELS: Record<string, string> = {
  revenue_by_business: "By Business",
  revenue_by_product: "By Product",
  revenue_by_geography: "By Geography",
};

function getSegmentPeriods(catData: SegmentCategory): string[] {
  return sortPeriods(Object.keys(catData));
}

function getSegmentNames(catData: SegmentCategory, periods: string[]): string[] {
  const names = new Set<string>();
  for (const periodMap of Object.values(catData)) {
    for (const seg of Object.keys(periodMap)) names.add(seg);
  }
  return [...names];
}

function isQuarterly(p: string) {
  return /^Q\d_FY\d{4}$/.test(p);
}

function toAnnualSegments(catData: SegmentCategory): { annualData: Record<string, Record<string, number | null>>; periods: string[]; incompleteFYs: Map<string, number> } {
  const allPeriods = getSegmentPeriods(catData);
  const segNames = getSegmentNames(catData, allPeriods);

  // Group quarterly periods by FY
  const fyMap: Record<string, string[]> = {};
  for (const p of allPeriods) {
    const m = p.match(/^Q\d_FY(\d{4})$/);
    if (!m) continue;
    const fy = `FY${m[1]}`;
    if (!fyMap[fy]) fyMap[fy] = [];
    fyMap[fy].push(p);
  }

  const annualData: Record<string, Record<string, number | null>> = {};
  for (const seg of segNames) {
    annualData[seg] = {};
    for (const [fy, quarters] of Object.entries(fyMap)) {
      const vals = quarters.map((q) => catData[q]?.[seg]?.value).filter((v): v is number => v != null);
      annualData[seg][fy] = vals.length > 0 ? vals.reduce((a, b) => a + b, 0) : null;
    }
  }

  const periods = Object.keys(fyMap).sort((a, b) => PERIOD_ORDER_WEIGHT(a) - PERIOD_ORDER_WEIGHT(b));
  const incompleteFYs = getIncompleteFYs(allPeriods.filter(isQuarterly));
  return { annualData, periods, incompleteFYs };
}

/* ================================================================
   GrowthToggle (same style as FinancialTable)
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
   SegmentTable Component
   ================================================================ */
interface SegmentTableProps {
  ticker: string;
  maxPeriods?: number;
  defaultView?: "quarterly" | "annual";
  defaultCategory?: string;
}

export default function SegmentTable({
  ticker,
  maxPeriods,
  defaultView = "quarterly",
  defaultCategory,
}: SegmentTableProps) {
  const { data: finData, loading, error } = useFinancialData(ticker);
  const data = useMemo(() => {
    if (!finData?._segments) return null;
    return { segments: finData._segments } as { segments: Record<string, SegmentCategory> };
  }, [finData]);
  const [viewMode, setViewMode] = useState<"quarterly" | "annual">(defaultView);
  const [growthMode, setGrowthMode] = useState<GrowthMode>("value");
  const [activeCategory, setActiveCategory] = useState<string>("");

  // Get available segment categories
  const categories = useMemo(() => {
    if (!data?.segments) return [];
    return Object.keys(data.segments).filter((k) => {
      const cat = data.segments![k];
      return cat && Object.keys(cat).length > 0;
    });
  }, [data]);

  // Set initial category
  useEffect(() => {
    if (categories.length > 0 && !activeCategory) {
      setActiveCategory(defaultCategory && categories.includes(defaultCategory) ? defaultCategory : categories[0]);
    }
  }, [categories, defaultCategory, activeCategory]);

  // Reset QoQ when switching to Annual
  useEffect(() => {
    if (viewMode === "annual" && growthMode === "qoq") setGrowthMode("value");
  }, [viewMode, growthMode]);

  if (loading) {
    return <div className="flex items-center justify-center py-10 text-sm text-[var(--text-faint)]">載入 Segment 數據中...</div>;
  }
  if (error || !data?.segments) {
    return <div className="py-6 text-center text-sm text-[var(--text-faint)]">{error ? `無法載入 ${ticker} Segment 數據：${error}` : "無 Segment 數據"}</div>;
  }
  if (!categories.length || !activeCategory) return null;

  const catData = data.segments[activeCategory];
  if (!catData) return null;

  // Build display data
  let periods: string[];
  let segVals: Record<string, Record<string, number | null>>; // segName → period → value
  let incompleteFYs = new Map<string, number>();

  if (viewMode === "annual") {
    const annual = toAnnualSegments(catData);
    periods = annual.periods;
    segVals = annual.annualData;
    incompleteFYs = annual.incompleteFYs;
  } else {
    periods = getSegmentPeriods(catData).filter(isQuarterly);
    const segNames = getSegmentNames(catData, periods);
    segVals = {};
    for (const seg of segNames) {
      segVals[seg] = {};
      for (const p of periods) {
        segVals[seg][p] = catData[p]?.[seg]?.value ?? null;
      }
    }
  }

  if (maxPeriods && maxPeriods > 0 && periods.length > maxPeriods) {
    periods = periods.slice(-maxPeriods);
  }

  const segNames = Object.keys(segVals);
  if (!segNames.length || !periods.length) return null;

  // Compute Total row
  const totalVals: Record<string, number | null> = {};
  for (const p of periods) {
    const vals = segNames.map((s) => segVals[s][p]).filter((v): v is number => v != null);
    totalVals[p] = vals.length > 0 ? vals.reduce((a, b) => a + b, 0) : null;
  }

  const isGrowth = growthMode !== "value";
  const prevFn = growthMode === "qoq" ? prevQoQ : prevYoY;
  const hasIncomplete = viewMode === "annual" && incompleteFYs.size > 0;

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
            const pk = prevFn(p);
            const prev = pk ? vals[pk] : null;
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
          const v = vals[p];
          const f = fmtVal(v, "revenue");
          return (
            <td
              key={p}
              className={`border border-[var(--border)] px-3 py-1.5 tabular-nums ${bgBase} ${isTotal ? "font-bold text-[#7b3f00]" : ""} ${
                f.cls === "negative" ? "text-right text-[#c0392b]" : f.cls === "null-val" ? "text-center text-[#7f8c8d]" : "text-right"
              }`}
            >
              {f.text}
            </td>
          );
        })}
      </tr>
    );
  };

  return (
    <div>
      {/* Controls */}
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <GrowthToggle mode={growthMode} setMode={setGrowthMode} isAnnual={viewMode === "annual"} />
          {categories.length > 1 && (
            <div className="flex gap-1">
              {categories.map((cat) => (
                <button
                  key={cat}
                  onClick={() => setActiveCategory(cat)}
                  className={`rounded border px-2.5 py-1 text-[11px] font-semibold transition-all select-none ${
                    activeCategory === cat
                      ? "border-[var(--text)] bg-[var(--text)] text-[var(--bg-card)]"
                      : "border-[var(--border)] bg-[var(--bg-subtle)] text-[var(--text-muted)] hover:border-[var(--text-muted)]"
                  }`}
                >
                  {CATEGORY_LABELS[cat] || cat}
                </button>
              ))}
            </div>
          )}
        </div>
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

      {/* Chart */}
      <div className="mb-4 rounded-md bg-[var(--bg-card)] p-4 shadow-sm">
        <div className="relative h-[260px]">
          <Line
            data={{
              labels: periods,
              datasets: segNames.map((name, i) => ({
                label: name,
                data: isGrowth
                  ? periods.map((p) => { const pk = prevFn(p); const g = growthPct(segVals[name]?.[p], pk ? segVals[name]?.[pk] : null); return g != null ? +(g * 100).toFixed(1) : null; })
                  : periods.map((p) => segVals[name]?.[p] ?? 0),
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
                tooltip: { callbacks: { label: (ctx) => isGrowth ? `${ctx.dataset.label}: ${ctx.parsed.y?.toFixed(1)}%` : `${ctx.dataset.label}: $${ctx.parsed.y}M` } },
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

      {/* Pie Chart */}
      <SegmentPieChart segVals={segVals} periods={periods} />

      {/* Table */}
      <div className="overflow-x-auto rounded-md shadow-sm">
        <table className="w-full border-collapse bg-[var(--bg-card)] text-xs">
          <thead>
            <tr>
              <th className="sticky left-0 z-[11] min-w-[140px] border border-[var(--border)] bg-[#1f4e79] px-3 py-1.5 text-left font-semibold text-white">
                Segment
              </th>
              {periods.map((p) => {
                const qCount = incompleteFYs.get(p);
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
            {segNames.map((seg, i) => renderRow(seg, segVals[seg], false, i))}
            {renderRow("Total", totalVals, true, segNames.length)}
          </tbody>
        </table>
      </div>

      <div className="mt-1.5 flex justify-between text-[10px]">
        {hasIncomplete && <span className="text-amber-600">* 數據未完整（僅部分季度），YoY 比較可能失真</span>}
        <span className="ml-auto text-[var(--text-faint)]">Source: NotebookLM / SEC EDGAR · Unit: $M</span>
      </div>
    </div>
  );
}
