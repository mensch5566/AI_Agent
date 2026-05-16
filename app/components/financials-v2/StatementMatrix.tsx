"use client";

import type { Cell, CellStatus } from "./types";
import type { Matrix } from "./useFinancialMatrix";
import { NONGAAP_SPOTLIGHT_METRICS, comparePeriods, fmtValue } from "./constants";

type Props = {
  gaap: Matrix;
  nongaap?: Matrix;
  showNongaapColumn?: boolean;
  signFlipConcepts?: string[];
};

function statusPresentation(status: CellStatus): { className: string } {
  switch (status) {
    case "SOURCE_OF_TRUTH":
      return { className: "text-foreground" };
    case "DERIVED_FROM_DISCLOSED":
      return { className: "italic text-muted-foreground" };
    case "EXCLUDED_FROM_NONGAAP":
      return { className: "line-through text-muted-foreground/60" };
    default:
      return { className: "italic text-muted-foreground/60" };
  }
}

function displayValue(c: Cell | undefined, signFlipConcepts: Set<string>): string {
  if (!c) return "—";
  const flip = !!c.xbrl_tag && signFlipConcepts.has(c.xbrl_tag);
  const v = flip ? -Math.abs(c.value) : c.value;
  if (v < 0) return `(${fmtValue(Math.abs(v), c.unit)})`;
  return fmtValue(v, c.unit);
}

function statusTooltip(status: CellStatus, c?: Cell): string {
  if (!c) return "pending — not derived yet";
  // Aggregated long-tail bucket — list children with their values.
  const prov = c.provenance as Record<string, unknown> | null;
  if (prov && prov.aggregation === "long_tail_sum") {
    const children = (prov.children as Array<Record<string, unknown>>) ?? [];
    const lines = children.map((ch) => {
      const sign = (ch.weight as number) === -1 ? "-" : "+";
      const rolls = ch.rolls_up_to ? ` → ${ch.rolls_up_to}` : "";
      return `${sign} ${ch.source_account}: ${ch.value}${rolls}`;
    });
    return `long-tail bucket (${children.length} child${children.length === 1 ? "" : "ren"}):\n${lines.join("\n")}`;
  }
  if (status === "DERIVED_FROM_DISCLOSED") {
    const f = prov?.formula;
    return f ? `derived: ${f}` : "derived";
  }
  if (status === "EXCLUDED_FROM_NONGAAP") return "excluded by Non-GAAP definition";
  if (status === "SOURCE_OF_TRUTH") {
    const f = prov?.source_filing;
    const a = prov?.accession_number;
    return `source: ${f ?? "filing"}${a ? ` (${a})` : ""}`;
  }
  return "";
}

export function StatementMatrix({
  gaap,
  nongaap,
  showNongaapColumn = false,
  signFlipConcepts = [],
}: Props) {
  const flipSet = new Set(signFlipConcepts);
  // Union of GAAP and Non-GAAP periods — Non-GAAP 8-K data may carry quarters
  // (e.g. Q4) that the GAAP feed hasn't derived yet, and we still want those
  // columns visible. GAAP-only cells show "—" in the Non-GAAP slot and vice
  // versa.
  const periods = (() => {
    if (!nongaap || !showNongaapColumn) return gaap.periods;
    const set = new Set<string>(gaap.periods);
    for (const p of nongaap.periods) set.add(p);
    return Array.from(set).sort(comparePeriods);
  })();

  if (periods.length === 0) {
    return <div className="p-4 text-sm text-muted-foreground">No data available for this view.</div>;
  }

  return (
    <div className="overflow-x-auto rounded border border-border bg-card">
      <table className="text-sm border-collapse w-full">
        <thead>
          <tr className="border-b border-border bg-muted">
            <th
              className="text-left px-3 py-2 sticky left-0 z-10 font-semibold text-foreground"
              style={{ background: "var(--muted)" }}
            >
              Metric
            </th>
            {periods.map((p) => (
              <th
                key={p}
                colSpan={showNongaapColumn ? 2 : 1}
                className="text-right px-3 py-2 whitespace-nowrap font-semibold text-foreground"
              >
                {p}
              </th>
            ))}
          </tr>
          {showNongaapColumn && (
            <tr className="border-b border-border text-xs text-muted-foreground">
              <th
                className="text-left px-3 py-1 sticky left-0 z-10"
                style={{ background: "var(--muted)" }}
              ></th>
              {periods.flatMap((p) => [
                <th key={`${p}-g`} className="text-right px-3 py-1">
                  GAAP
                </th>,
                <th key={`${p}-n`} className="text-right px-3 py-1">
                  Non-GAAP
                </th>,
              ])}
            </tr>
          )}
        </thead>
        <tbody>
          {gaap.rows.map((row) => {
            const isSubtotal = row.kind === "subtotal";
            const isLongTail = row.kind === "long_tail_bucket";
            const isDerivedRow = row.kind === "derived_ratio";
            const showNgForThisRow =
              showNongaapColumn && NONGAAP_SPOTLIGHT_METRICS.has(row.key);
            const indentPx = (row.indent ?? 0) * 12;
            const rowBg = isSubtotal ? "var(--muted)" : "var(--card)";
            return (
              <tr
                key={row.key}
                className={
                  "border-b border-border " +
                  (isSubtotal ? "font-semibold " : "") +
                  (isDerivedRow ? "italic " : "")
                }
                style={{ background: rowBg }}
              >
                <td
                  className={
                    "px-3 py-1.5 sticky left-0 z-10 " +
                    (isLongTail ? "italic text-muted-foreground" : "text-foreground")
                  }
                  style={{ paddingLeft: 12 + indentPx, background: rowBg }}
                >
                  {row.label}
                </td>
                {periods.flatMap((p) => {
                  const m = gaap.cells[row.key]?.[p];
                  const c = m?.cell;
                  const ngCellWrap = showNgForThisRow ? nongaap?.cells[row.key]?.[p] : undefined;
                  const ng = ngCellWrap?.cell;
                  const pres = statusPresentation(m?.status ?? "PENDING");
                  const cells = [
                    <td
                      key={`${row.key}-${p}-g`}
                      className={`text-right px-3 py-1.5 whitespace-nowrap ${pres.className}`}
                      title={statusTooltip(m?.status ?? "PENDING", c)}
                    >
                      {displayValue(c, flipSet)}
                    </td>,
                  ];
                  // Whenever the table-wide Non-GAAP column is on, we MUST
                  // render a second <td> per period so cells align with the
                  // colSpan=2 header. Rows not in NONGAAP_SPOTLIGHT_METRICS
                  // get a placeholder dash instead of a real Non-GAAP value.
                  if (showNongaapColumn) {
                    if (showNgForThisRow) {
                      const npres = statusPresentation(ngCellWrap?.status ?? "PENDING");
                      cells.push(
                        <td
                          key={`${row.key}-${p}-n`}
                          className={`text-right px-3 py-1.5 whitespace-nowrap ${npres.className}`}
                          title={
                            ng
                              ? statusTooltip(ngCellWrap?.status ?? "PENDING", ng)
                              : "not disclosed by management"
                          }
                        >
                          {displayValue(ng, flipSet)}
                        </td>,
                      );
                    } else {
                      cells.push(
                        <td
                          key={`${row.key}-${p}-n`}
                          className="text-right px-3 py-1.5 whitespace-nowrap text-muted-foreground/40"
                          title="no Non-GAAP spotlight for this metric"
                        >
                          —
                        </td>,
                      );
                    }
                  }
                  return cells;
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
