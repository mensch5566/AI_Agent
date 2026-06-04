"use client";

// Derived / Non-GAAP ABSOLUTE-VALUE subsection (Task 13, spec §P2.3).
//
// Renders the $ derived measures (EBITDA from the IS metrics, Free Cash Flow
// from the CF metrics) that are deliberately NOT shown inline in the
// PDF-faithful IS/CF statements and are NOT ratios. Values are formatted with
// the statement-scoped $ formatter (fmtStatementValue) — whole dollars with
// separators, parens for negatives — exactly like the statements, since these
// are dollar amounts, not percentages. Each row carries the shared "non-GAAP"
// superscript + tooltip (NONGAAP_DERIVED_ROWS) so it reads as a derived measure.

import type { CellStatus } from "./types";
import type { Matrix } from "./useFinancialMatrix";
import {
  NONGAAP_DERIVED_ROWS,
  NONGAAP_DERIVED_TOOLTIP,
  NONGAAP_DERIVED_TOOLTIP_FALLBACK,
  fmtValue,
} from "./constants";
import { fmtStatementValue } from "./statementFormat";

type Props = {
  /** Built via buildDerivedNonGaapRows(cells, version, frequency). */
  matrix: Matrix;
};

function statusClass(status: CellStatus): string {
  switch (status) {
    case "SOURCE_OF_TRUTH":
      return "text-foreground";
    case "DERIVED_FROM_DISCLOSED":
      return "italic text-muted-foreground";
    default:
      return "italic text-muted-foreground/60";
  }
}

export function DerivedNonGaapMatrix({ matrix }: Props) {
  const { periods, rows, cells } = matrix;

  return (
    <section className="mt-6">
      <h2 className="text-sm font-semibold text-foreground mb-1">Derived / Non-GAAP</h2>
      <p className="text-xs text-muted-foreground mb-2">
        Derived $ measures (EBITDA, Free Cash Flow) — computed from GAAP inputs,
        not reported GAAP line items. Shown here rather than inline so the
        statements stay PDF-faithful.
      </p>
      {periods.length === 0 ? (
        <div className="p-3 text-sm text-muted-foreground rounded border border-border bg-card">
          No derived measures available for this view.
        </div>
      ) : (
        <div className="overflow-x-auto rounded border border-border bg-card">
          <table className="text-sm border-collapse w-full">
            <thead>
              <tr className="border-b border-border bg-muted">
                <th
                  className="text-left px-3 py-2 sticky left-0 z-10 font-semibold text-foreground"
                  style={{ background: "var(--muted)" }}
                >
                  Measure
                </th>
                {periods.map((p) => (
                  <th
                    key={p}
                    className="text-right px-3 py-2 whitespace-nowrap font-semibold text-foreground"
                  >
                    {p}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.key} className="border-b border-border" style={{ background: "var(--card)" }}>
                  <td
                    className="px-3 py-1.5 sticky left-0 z-10 text-foreground"
                    style={{ background: "var(--card)" }}
                  >
                    {row.label}
                    {NONGAAP_DERIVED_ROWS.has(row.key) && (
                      <sup
                        className="ml-0.5 text-[9px] font-medium text-muted-foreground cursor-help"
                        title={NONGAAP_DERIVED_TOOLTIP[row.key] ?? NONGAAP_DERIVED_TOOLTIP_FALLBACK}
                        aria-label="non-GAAP derived measure"
                      >
                        non-GAAP
                      </sup>
                    )}
                  </td>
                  {periods.map((p) => {
                    const m = cells[row.key]?.[p];
                    const c = m?.cell;
                    // $ absolute values → statement-scoped formatter. It owns
                    // money/EPS and returns null for anything else, in which
                    // case fall back to fmtValue (defensive; these are $).
                    let text = "—";
                    if (c) {
                      const scoped = fmtStatementValue(c.value, c.unit);
                      text = scoped !== null ? scoped : fmtValue(c.value, c.unit, c.uni_account);
                    }
                    return (
                      <td
                        key={`${row.key}-${p}`}
                        className={`text-right px-3 py-1.5 whitespace-nowrap ${statusClass(m?.status ?? "PENDING")}`}
                      >
                        {text}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
