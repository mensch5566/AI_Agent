"use client";

/* eslint-disable @typescript-eslint/no-explicit-any */
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
  sortPeriods, fmtVal, CHART_COLORS,
  type GrowthMode, prevQoQ, prevYoY, growthPct, fmtGrowth,
} from "./constants";
import { useFinancialData } from "./useFinancialData";

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Legend);

const CATEGORY_LABELS: Record<string, string> = {
  revenue_by_business: "By Business",
  profit_by_business: "By Business Profit",
  revenue_by_product: "By Product",
  revenue_by_geography: "By Geography",
};

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

interface SegmentTableProps {
  ticker: string;
  maxPeriods?: number;
  defaultView?: "quarterly" | "annual";
  defaultCategory?: string;
}

export default function SegmentTable({
  ticker, maxPeriods, defaultView = "quarterly", defaultCategory,
}: SegmentTableProps) {
  const { store, loading, error } = useFinancialData(ticker);
  const [viewMode, setViewMode] = useState<"quarterly" | "annual">(defaultView);
  const [growthMode, setGrowthMode] = useState<GrowthMode>("value");
  const [activeCategory, setActiveCategory] = useState<string>("");

  const categories = useMemo(() => {
    if (!store) return [];
    return store.segmentCategories().filter((c) => store.dimensions("segments", c).length > 0);
  }, [store]);

  useEffect(() => {
    if (categories.length > 0 && !activeCategory) {
      setActiveCategory(defaultCategory && categories.includes(defaultCategory) ? defaultCategory : categories[0]);
    }
  }, [categories, defaultCategory, activeCategory]);

  useEffect(() => { if (viewMode === "annual" && growthMode === "qoq") setGrowthMode("value"); }, [viewMode, growthMode]);

  if (loading) return <div className="flex items-center justify-center py-10 text-sm text-[var(--text-faint)]">載入 Segment 數據中...</div>;
  if (error || !store) return <div className="py-6 text-center text-sm text-[var(--text-faint)]">{error ? `無法載入 ${ticker} Segment 數據：${error}` : "無 Segment 數據"}</div>;
  if (!categories.length || !activeCategory) return null;

  const segData = store.segmentData(activeCategory);
  const names = Object.keys(segData);
  const allPeriods = store.segmentPeriods(activeCategory);
  const quarterlyPeriods = sortPeriods(allPeriods.filter((p) => /^Q\d_FY\d+$/.test(p)));
  const annualDirectPeriods = sortPeriods(allPeriods.filter((p) => /^FY\d+$/.test(p)));
  const samplePeriod = allPeriods[0] ?? "";
  const sampleName = names[0] ?? "";
  const segmentUnit = samplePeriod && sampleName ? store.unit("segments", activeCategory, samplePeriod, sampleName) : null;

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

  // Build segVals with optional annual aggregation
  let periods: string[];
  const segVals: Record<string, Record<string, number | null>> = {};

  if (viewMode === "annual") {
    const fySet = new Set<string>(annualDirectPeriods);
    for (const p of quarterlyPeriods) { const m = p.match(/Q\d_FY(\d+)/); if (m) fySet.add(`FY${m[1]}`); }
    periods = sortPeriods([...fySet]);
    for (const name of names) {
      segVals[name] = {};
      const fyMap: Record<string, number[]> = {};
      const directAnnual: Record<string, number> = {};
      for (const [p, v] of Object.entries(segData[name])) {
        if (v == null) continue;
        const direct = p.match(/^FY(\d+)$/);
        if (direct) {
          directAnnual[`FY${direct[1]}`] = v;
          continue;
        }
        const m = p.match(/Q\d_FY(\d+)/); if (!m) continue;
        const fy = `FY${m[1]}`; if (!fyMap[fy]) fyMap[fy] = []; fyMap[fy].push(v);
      }
      for (const fy of periods) {
        if (directAnnual[fy] != null) {
          segVals[name][fy] = directAnnual[fy];
          continue;
        }
        const vals = fyMap[fy];
        segVals[name][fy] = vals?.length ? vals.reduce((a, b) => a + b, 0) : null;
      }
    }
  } else {
    periods = quarterlyPeriods;
    for (const name of names) {
      segVals[name] = {};
      for (const p of periods) segVals[name][p] = segData[name][p] ?? null;
    }
  }

  if (maxPeriods && maxPeriods > 0 && periods.length > maxPeriods) periods = periods.slice(-maxPeriods);
  if (!names.length || !periods.length) return null;

  const totalVals: Record<string, number | null> = {};
  for (const p of periods) {
    const vals = names.map((s) => segVals[s][p]).filter((v): v is number => v != null);
    totalVals[p] = vals.length > 0 ? vals.reduce((a, b) => a + b, 0) : null;
  }
  const pieEligiblePeriods = periods.filter((p) => names.every((n) => (segVals[n]?.[p] ?? 0) >= 0));

  const isGrowth = growthMode !== "value";
  const prevFn = growthMode === "qoq" ? prevQoQ : prevYoY;

  const renderRow = (label: string, vals: Record<string, number | null>, isTotal: boolean, idx: number) => {
    const bgBase = isTotal ? "bg-[var(--bg-highlight)]" : idx % 2 === 0 ? "bg-[var(--bg-subtle)]" : "bg-[var(--bg-card)]";
    return (
      <tr key={label}>
        <td className={`sticky left-0 z-[5] border border-[var(--border)] px-3 py-1.5 text-left font-medium whitespace-nowrap ${bgBase} ${isTotal ? "font-bold text-[#7b3f00]" : ""}`}>{label}</td>
        {periods.map((p) => {
          if (isGrowth) {
            const curr = vals[p]; const pk = prevFn(p); const prev = pk ? vals[pk] : null;
            const g = growthPct(curr, prev); const f = fmtGrowth(g);
            return (
              <td key={p} className={`border border-[var(--border)] px-3 py-1.5 tabular-nums ${bgBase} ${
                f.cls === "negative" ? "text-right text-[#c0392b]" : f.cls === "positive" ? "text-right text-[#27ae60]" : f.cls === "null-val" ? "text-center text-[#7f8c8d]" : "text-right"
              }`}>{f.text}</td>
            );
          }
          const v = vals[p]; const f = fmtVal(v, "revenue");
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
    <div>
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <GrowthToggle mode={growthMode} setMode={setGrowthMode} isAnnual={viewMode === "annual"} />
          {categories.length > 1 && (
            <div className="flex gap-1">
              {categories.map((cat) => (
                <button key={cat} onClick={() => setActiveCategory(cat)}
                  className={`rounded border px-2.5 py-1 text-[11px] font-semibold transition-all select-none ${
                    activeCategory === cat ? "border-[var(--text)] bg-[var(--text)] text-[var(--bg-card)]" : "border-[var(--border)] bg-[var(--bg-subtle)] text-[var(--text-muted)] hover:border-[var(--text-muted)]"
                  }`}
                >{CATEGORY_LABELS[cat] || cat}</button>
              ))}
            </div>
          )}
        </div>
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

      <div className="mb-4 rounded-md bg-[var(--bg-card)] p-4 shadow-sm">
        <div className="relative h-[260px]">
          <Line data={{
            labels: periods,
            datasets: names.map((name, i) => ({
              label: name,
              data: isGrowth
                ? periods.map((p) => { const pk = prevFn(p); const g = growthPct(segVals[name]?.[p], pk ? segVals[name]?.[pk] : null); return g != null ? +(g * 100).toFixed(1) : null; })
                : periods.map((p) => segVals[name]?.[p] ?? 0),
              borderColor: CHART_COLORS[i % CHART_COLORS.length],
              backgroundColor: CHART_COLORS[i % CHART_COLORS.length] + "cc",
              tension: 0.3, pointRadius: 3,
            })),
          }} options={{
            responsive: true, maintainAspectRatio: false,
            interaction: { mode: "index" as const, intersect: false },
            plugins: {
              tooltip: { callbacks: { label: (ctx) => isGrowth ? `${ctx.dataset.label}: ${ctx.parsed.y?.toFixed(1)}%` : `${ctx.dataset.label}: ${formatSegmentValue(ctx.parsed.y ?? 0)}` } },
              legend: { position: "bottom" as const, labels: { boxWidth: 12, font: { size: 11 } } },
            },
            scales: {
              x: { ticks: { font: { size: 10 }, maxRotation: 45 } },
              y: { ticks: { font: { size: 10 }, callback: (v) => isGrowth ? `${v}%` : segmentTickLabel(v) } },
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
              <th className="sticky left-0 z-[11] min-w-[140px] border border-[var(--border)] bg-[#1f4e79] px-3 py-1.5 text-left font-semibold text-white">Segment</th>
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
      <div className="mt-1.5 text-right text-[10px] text-[var(--text-faint)]">
        Source: NotebookLM / SEC EDGAR · Unit: {segmentUnit === "TWD_thousands" ? "TWD thousands" : segmentUnit === "USD_thousands" ? "USD thousands" : "reported value"}
      </div>
    </div>
  );
}
