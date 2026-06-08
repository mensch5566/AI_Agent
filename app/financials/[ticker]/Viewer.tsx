"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useFinancialData, buildMatrix, buildDerivedNonGaapRows, type Frequency } from "@/app/components/financials-v2/useFinancialMatrix";
import { StatementMatrix } from "@/app/components/financials-v2/StatementMatrix";
import { DerivedNonGaapMatrix } from "@/app/components/financials-v2/DerivedNonGaapMatrix";
import { MatrixChart } from "@/app/components/financials-v2/MatrixChart";
import { SegmentDashboard } from "@/app/components/financials-v2/SegmentDashboard";
import { TickerPicker } from "@/app/components/financials-v2/TickerPicker";
import {
  CHART_DEFAULT_KEYS,
  CHART_MAX_SELECTION,
  chartGroupOf,
} from "@/app/components/financials-v2/constants";
import type { Statement } from "@/app/components/financials-v2/types";
import ThemeToggle from "@/app/components/ThemeToggle";
import { Button } from "@/components/ui/button";

type View = Statement | "SEGMENT";

const VIEWS: { key: View; label: string }[] = [
  { key: "IS", label: "Income Statement" },
  { key: "BS", label: "Balance Sheet" },
  { key: "CF", label: "Cash Flow" },
  { key: "RATIO", label: "Ratios" },
  { key: "SEGMENT", label: "Segment / Geo" },
];

export default function Viewer({ ticker }: { ticker: string }) {
  const { loading, error, data } = useFinancialData(ticker);
  const [view, setView] = useState<View>("IS");
  const [frequency, setFrequency] = useState<Frequency>("quarterly");
  const [showNonGaap, setShowNonGaap] = useState(false);
  // Statement render mode: 'pdf' = filing-faithful (data-driven), 'uni' = canonical
  // uni_account rows + long-tail buckets. Persisted in localStorage (hydration-safe).
  const [viewMode, setViewMode] = useState<"pdf" | "uni">("pdf");
  const [modeHydrated, setModeHydrated] = useState(false);

  const cells = data?.cells ?? [];
  const dimensional = data?.dimensional ?? [];
  const signFlip = data?.company.sign_flip_concepts ?? [];

  const statement: Statement = view === "SEGMENT" ? "IS" : view;

  const gaapMatrix = useMemo(
    () => buildMatrix(cells, statement, "GAAP", frequency, viewMode),
    [cells, statement, frequency, viewMode],
  );
  const nongaapMatrix = useMemo(
    () => buildMatrix(cells, statement, "NON_GAAP", frequency),
    [cells, statement, frequency],
  );

  // Derived / Non-GAAP absolute-value $ rows (EBITDA, FCF) — surfaced only in
  // the Ratios/analytics area, never inline in the statements (spec §P2.3).
  const derivedNonGaapMatrix = useMemo(
    () => buildDerivedNonGaapRows(cells, "GAAP", frequency),
    [cells, frequency],
  );

  const showNongaapCol = showNonGaap && view === "IS";

  // ---- Chart selection state (shared between MatrixChart and StatementMatrix) ----
  //
  // selectedKeys is an ordered list (FIFO): clicking a 4th row evicts the
  // oldest. Clicking a row with an incompatible unit group (e.g. % when the
  // current selection is $) resets the list — keeps the chart's single axis
  // honest without surfacing a modal.
  //
  // rowsWithData drives which rows are clickable; rows that are all-PENDING
  // in the matrix can't contribute a line.
  // Lazy init with the IS preset so the chart shows something on the very
  // first paint (before useEffect[statement] runs). The slice() guards
  // against future preset lists outgrowing CHART_MAX_SELECTION.
  const [selectedKeys, setSelectedKeys] = useState<string[]>(() =>
    (CHART_DEFAULT_KEYS.IS ?? []).slice(0, CHART_MAX_SELECTION),
  );

  const rowsWithData = useMemo(() => {
    const out = new Set<string>();
    for (const row of gaapMatrix.rows) {
      for (const p of gaapMatrix.periods) {
        if (gaapMatrix.cells[row.key]?.[p]?.cell) {
          out.add(row.key);
          break;
        }
      }
    }
    if (showNongaapCol) {
      for (const row of nongaapMatrix.rows) {
        if (out.has(row.key)) continue;
        for (const p of nongaapMatrix.periods) {
          if (nongaapMatrix.cells[row.key]?.[p]?.cell) {
            out.add(row.key);
            break;
          }
        }
      }
    }
    return out;
  }, [gaapMatrix, nongaapMatrix, showNongaapCol]);

  // Reset chart selection when the statement changes: apply that
  // statement's preset. We don't filter by rowsWithData here — keys that
  // lack data render as empty lines but stay selectable; the issuer-
  // specific gaps are usually obvious to the analyst.
  // Also reset on viewMode change: uni rows key by uni_account, pdf rows by rowId,
  // so a stale PDF-only selection would silently null the chart after switching.
  useEffect(() => {
    setSelectedKeys((CHART_DEFAULT_KEYS[statement] ?? []).slice(0, CHART_MAX_SELECTION));
  }, [statement, viewMode]);

  // Read persisted view mode once on mount (App Router: never read localStorage in
  // a useState initializer — SSR has no window).
  useEffect(() => {
    const saved = typeof window !== "undefined"
      ? window.localStorage.getItem("fin-view-mode-v1")
      : null;
    if (saved === "pdf" || saved === "uni") setViewMode(saved);
    setModeHydrated(true);
  }, []);

  // Persist — guarded so the initial 'pdf' render never overwrites a stored 'uni'
  // before the read effect commits.
  useEffect(() => {
    if (!modeHydrated) return;
    window.localStorage.setItem("fin-view-mode-v1", viewMode);
  }, [viewMode, modeHydrated]);

  // Look up a row's unit by peeking the first populated cell in the GAAP
  // matrix (falls back to Non-GAAP if GAAP has no value yet — e.g. Q4 from
  // 8-K only).
  const unitOfRow = useCallback(
    (key: string): string => {
      for (const p of gaapMatrix.periods) {
        const c = gaapMatrix.cells[key]?.[p]?.cell;
        if (c) return c.unit;
      }
      for (const p of nongaapMatrix.periods) {
        const c = nongaapMatrix.cells[key]?.[p]?.cell;
        if (c) return c.unit;
      }
      return "";
    },
    [gaapMatrix, nongaapMatrix],
  );

  const handleToggleRow = useCallback(
    (key: string) => {
      setSelectedKeys((prev) => {
        if (prev.includes(key)) {
          return prev.filter((k) => k !== key);
        }
        const newGroup = chartGroupOf(unitOfRow(key), key);
        const currentGroup = prev.length > 0 ? chartGroupOf(unitOfRow(prev[0]), prev[0]) : null;
        if (currentGroup && newGroup !== currentGroup) {
          // Different unit group → swap modes, keep only the new row.
          return [key];
        }
        if (prev.length >= CHART_MAX_SELECTION) {
          // FIFO evict oldest.
          return [...prev.slice(1), key];
        }
        return [...prev, key];
      });
    },
    [unitOfRow],
  );

  return (
    <main className="max-w-screen-2xl mx-auto p-6 text-foreground">
      <header className="mb-6 flex items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <TickerPicker current={ticker} />
          <div>
            <h1 className="text-2xl font-semibold leading-tight">
              {data?.company.company_name || ticker}
              <span className="text-base font-normal text-muted-foreground ml-2">
                {data?.company.exchange}
              </span>
            </h1>
            {data && (
              <div className="text-xs text-muted-foreground mt-0.5">
                CIK {data.company.cik} · FY-end month {data.company.fiscal_year_end_month}
                {" · "}{data.counts.facts} facts · {data.counts.metrics} metrics · {data.counts.dimensional} dim
              </div>
            )}
          </div>
        </div>
        <ThemeToggle />
      </header>

      {loading && <div className="text-sm text-muted-foreground">Loading…</div>}
      {error && (
        <div className="text-sm text-destructive border border-destructive/30 bg-accent px-3 py-2 rounded">
          {error}
        </div>
      )}

      {data && (
        <>
          <div className="flex flex-wrap items-center gap-2 mb-4">
            <div className="inline-flex rounded-md border border-border overflow-hidden">
              {VIEWS.map((v) => (
                <Button
                  key={v.key}
                  size="sm"
                  variant={view === v.key ? "default" : "ghost"}
                  onClick={() => setView(v.key)}
                  className="rounded-none border-r last:border-r-0 border-border"
                >
                  {v.label}
                </Button>
              ))}
            </div>

            {view !== "SEGMENT" && (
              <div className="inline-flex rounded-md border border-border overflow-hidden ml-2">
                {(["quarterly", "annual"] as Frequency[]).map((f) => (
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
            )}

            {(view === "IS" || view === "BS" || view === "CF") && (
              <div
                className="inline-flex rounded-md border border-border overflow-hidden ml-2"
                role="group"
                aria-label="statement view mode"
              >
                {([["pdf", "依財報"], ["uni", "標準科目"]] as const).map(([m, label]) => (
                  <Button
                    key={m}
                    size="sm"
                    variant={viewMode === m ? "default" : "ghost"}
                    aria-pressed={viewMode === m}
                    onClick={() => setViewMode(m)}
                    className="rounded-none border-r last:border-r-0 border-border"
                  >
                    {label}
                  </Button>
                ))}
              </div>
            )}

            {view === "IS" && (
              <button
                type="button"
                role="switch"
                aria-checked={showNonGaap}
                onClick={() => setShowNonGaap((v) => !v)}
                className="inline-flex items-center gap-2 text-sm ml-2 select-none cursor-pointer"
                title={showNonGaap ? "Hide Non-GAAP spotlight" : "Show Non-GAAP spotlight"}
              >
                <span
                  className={
                    "relative inline-block w-9 h-5 rounded-full transition-colors " +
                    (showNonGaap ? "bg-primary" : "bg-muted-foreground/30")
                  }
                >
                  <span
                    className={
                      "absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform " +
                      (showNonGaap ? "translate-x-4" : "translate-x-0")
                    }
                  />
                </span>
                Non-GAAP spotlight
              </button>
            )}
          </div>

          {view === "SEGMENT" ? (
            <SegmentDashboard dimensional={dimensional} />
          ) : (
            <>
              <MatrixChart
                gaap={gaapMatrix}
                nongaap={nongaapMatrix}
                selectedKeys={selectedKeys}
                showNongaapColumn={showNongaapCol}
              />
              <StatementMatrix
                statement={statement}
                gaap={gaapMatrix}
                nongaap={nongaapMatrix}
                showNongaapColumn={showNongaapCol}
                signFlipConcepts={signFlip}
                selectedKeys={selectedKeys}
                onToggleRow={handleToggleRow}
                rowsWithData={rowsWithData}
              />
              {view === "RATIO" && (
                <DerivedNonGaapMatrix matrix={derivedNonGaapMatrix} />
              )}
            </>
          )}

          <div className="mt-6 text-xs text-muted-foreground space-y-1">
            <div>
              <span
                className="inline-block w-3 h-3 align-middle mr-1"
                style={{ background: "var(--text)" }}
              />
              SOURCE_OF_TRUTH
            </div>
            <div>
              <span className="italic mr-1" style={{ color: "var(--text-muted)" }}>italic muted</span>
              DERIVED_FROM_DISCLOSED (hover for formula)
            </div>
            <div>
              <span className="italic mr-1" style={{ color: "var(--text-faint)" }}>— pending</span>
              derived value not yet computed
            </div>
          </div>
        </>
      )}
    </main>
  );
}
