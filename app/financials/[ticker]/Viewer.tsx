"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useFinancialData, buildMatrix, type Frequency } from "@/app/components/financials-v2/useFinancialMatrix";
import { StatementMatrix } from "@/app/components/financials-v2/StatementMatrix";
import { MatrixChart } from "@/app/components/financials-v2/MatrixChart";
import { SegmentDashboard } from "@/app/components/financials-v2/SegmentDashboard";
import { TickerPicker } from "@/app/components/financials-v2/TickerPicker";
import {
  CHART_DEFAULT_KEYS,
  CHART_MAX_SELECTION,
  unitGroupOf,
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
  const [showNonGaap, setShowNonGaap] = useState(true);

  const cells = data?.cells ?? [];
  const dimensional = data?.dimensional ?? [];
  const signFlip = data?.company.sign_flip_concepts ?? [];

  const statement: Statement = view === "SEGMENT" ? "IS" : view;

  const gaapMatrix = useMemo(
    () => buildMatrix(cells, statement, "GAAP", frequency),
    [cells, statement, frequency],
  );
  const nongaapMatrix = useMemo(
    () => buildMatrix(cells, statement, "NON_GAAP", frequency),
    [cells, statement, frequency],
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
  useEffect(() => {
    setSelectedKeys((CHART_DEFAULT_KEYS[statement] ?? []).slice(0, CHART_MAX_SELECTION));
  }, [statement]);

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
        const newGroup = unitGroupOf(unitOfRow(key));
        const currentGroup = prev.length > 0 ? unitGroupOf(unitOfRow(prev[0])) : null;
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

            {view === "IS" && (
              <label className="inline-flex items-center gap-1 text-sm ml-2">
                <input
                  type="checkbox"
                  checked={showNonGaap}
                  onChange={(e) => setShowNonGaap(e.target.checked)}
                />
                Non-GAAP spotlight
              </label>
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
                gaap={gaapMatrix}
                nongaap={nongaapMatrix}
                showNongaapColumn={showNongaapCol}
                signFlipConcepts={signFlip}
                selectedKeys={selectedKeys}
                onToggleRow={handleToggleRow}
                rowsWithData={rowsWithData}
              />
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
