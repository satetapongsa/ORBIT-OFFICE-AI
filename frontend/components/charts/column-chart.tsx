"use client";

import { useId, useState } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export interface ColumnSeries {
  key: string;
  label: string;
  /** CSS colour (use theme variables, e.g. `var(--chart-1)`). */
  color: string;
}

export interface ColumnDatum {
  key: string;
  /** Short axis label (e.g. "11"). */
  label: string;
  /** Full label for the tooltip and table (e.g. "11 พ.ย. 2569"). */
  fullLabel: string;
  values: Record<string, number>;
}

interface ColumnChartProps {
  /** Accessible name of the chart (the visible title lives in the surrounding card). */
  title: string;
  data: ColumnDatum[];
  series: ColumnSeries[];
  /** Unit appended to values in tooltips/table, e.g. "ครั้ง". */
  unit?: string;
  heightClassName?: string;
}

const formatter = new Intl.NumberFormat("th-TH");

/**
 * Smallest round ceiling ≥ value whose half is a whole number, so the three gridlines
 * (0, half, max) are integer counts. Minimum 4.
 */
export function niceMax(value: number): number {
  if (value <= 4) return 4;
  const magnitude = 10 ** Math.floor(Math.log10(value));
  for (const step of [2, 2.5, 3, 4, 5, 6, 8, 10]) {
    const candidate = step * magnitude;
    if (candidate >= value && candidate % 2 === 0) return candidate;
  }
  return 10 * magnitude;
}

/**
 * Vertical (stacked) column chart in plain HTML: thin columns from one baseline, recessive
 * gridlines, a hover/focus tooltip per column, a legend for ≥ 2 series and a table view.
 */
export function ColumnChart({
  title,
  data,
  series,
  unit = "",
  heightClassName = "h-40",
}: ColumnChartProps) {
  const [active, setActive] = useState<number | null>(null);
  const [showTable, setShowTable] = useState(false);
  const tableId = useId();
  const totals = data.map((d) => series.reduce((sum, s) => sum + (d.values[s.key] ?? 0), 0));
  const max = niceMax(Math.max(0, ...totals));
  const ticks = [max, max / 2, 0];
  const withUnit = (n: number) => `${formatter.format(n)}${unit ? ` ${unit}` : ""}`;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        {series.length > 1 ? (
          <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs" aria-label="คำอธิบายสัญลักษณ์">
            {series.map((s) => (
              <li key={s.key} className="text-muted-foreground flex items-center gap-1.5">
                <span className="size-2.5 rounded-sm" style={{ backgroundColor: s.color }} />
                {s.label}
              </li>
            ))}
          </ul>
        ) : (
          <span />
        )}
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-7 text-xs"
          aria-expanded={showTable}
          aria-controls={tableId}
          onClick={() => setShowTable((v) => !v)}
        >
          {showTable ? "ดูเป็นกราฟ" : "ดูเป็นตาราง"}
        </Button>
      </div>

      {showTable ? (
        <div id={tableId} className="max-h-64 overflow-auto rounded-lg border">
          <table className="w-full text-sm">
            <caption className="sr-only">{title}</caption>
            <thead className="bg-muted/50 text-muted-foreground text-xs">
              <tr>
                <th scope="col" className="px-3 py-2 text-left font-medium">
                  วันที่
                </th>
                {series.map((s) => (
                  <th key={s.key} scope="col" className="px-3 py-2 text-right font-medium">
                    {s.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.map((d) => (
                <tr key={d.key} className="border-t">
                  <th scope="row" className="px-3 py-1.5 text-left font-normal">
                    {d.fullLabel}
                  </th>
                  {series.map((s) => (
                    <td key={s.key} className="px-3 py-1.5 text-right tabular-nums">
                      {formatter.format(d.values[s.key] ?? 0)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div role="group" aria-label={title} className="flex gap-2">
          <div
            aria-hidden
            className={cn(
              "text-muted-foreground flex flex-col justify-between text-right text-[10px] tabular-nums",
              heightClassName,
            )}
          >
            {ticks.map((t) => (
              <span key={t} className="-my-1.5 leading-3">
                {formatter.format(t)}
              </span>
            ))}
          </div>
          <div className="min-w-0 flex-1">
            <div className={cn("relative", heightClassName)}>
              {/* Recessive gridlines: top, middle, baseline. */}
              <div aria-hidden className="absolute inset-0 flex flex-col justify-between">
                <div className="border-border/70 border-t border-dashed" />
                <div className="border-border/70 border-t border-dashed" />
                <div className="border-foreground/20 border-t" />
              </div>
              <ol className="absolute inset-0 flex items-stretch">
                {data.map((d, index) => {
                  const total = totals[index] ?? 0;
                  const parts = series
                    .map((s) => ({ series: s, value: d.values[s.key] ?? 0 }))
                    .filter((p) => p.value > 0);
                  const description = `${d.fullLabel}: ${series
                    .map((s) => `${s.label} ${withUnit(d.values[s.key] ?? 0)}`)
                    .join(", ")}`;
                  return (
                    <li
                      key={d.key}
                      tabIndex={0}
                      aria-label={description}
                      data-testid={`column-${d.key}`}
                      onMouseEnter={() => setActive(index)}
                      onMouseLeave={() => setActive(null)}
                      onFocus={() => setActive(index)}
                      onBlur={() => setActive(null)}
                      className="group focus-visible:ring-ring/50 relative flex flex-1 flex-col items-center justify-end rounded-sm outline-none focus-visible:ring-2"
                    >
                      <div
                        className="flex w-full max-w-6 flex-col-reverse gap-[2px]"
                        style={{ height: `${(total / max) * 100}%` }}
                      >
                        {parts.map((p, partIndex) => (
                          <div
                            key={p.series.key}
                            className={cn(
                              "min-h-[2px] w-full transition-opacity",
                              partIndex === parts.length - 1 && "rounded-t-[4px]",
                              active !== null && active !== index && "opacity-50",
                            )}
                            style={{ backgroundColor: p.series.color, flexGrow: p.value }}
                          />
                        ))}
                      </div>
                      {active === index ? (
                        <div
                          role="tooltip"
                          className="bg-popover text-popover-foreground pointer-events-none absolute bottom-full z-10 mb-1 w-max max-w-48 rounded-md border px-2.5 py-1.5 text-xs shadow-md"
                        >
                          <p className="font-medium">{d.fullLabel}</p>
                          {series.map((s) => (
                            <p
                              key={s.key}
                              className="text-muted-foreground flex items-center gap-1.5"
                            >
                              <span
                                className="size-2 rounded-sm"
                                style={{ backgroundColor: s.color }}
                              />
                              {s.label}
                              <span className="text-foreground ml-auto pl-2 tabular-nums">
                                {withUnit(d.values[s.key] ?? 0)}
                              </span>
                            </p>
                          ))}
                        </div>
                      ) : null}
                    </li>
                  );
                })}
              </ol>
            </div>
            <ol aria-hidden className="mt-1.5 flex">
              {data.map((d, index) => (
                <li
                  key={d.key}
                  className={cn(
                    "text-muted-foreground flex-1 text-center text-[10px] tabular-nums",
                    // Every other label on narrow screens keeps the axis legible.
                    index % 2 === 1 && "max-sm:invisible",
                  )}
                >
                  {d.label}
                </li>
              ))}
            </ol>
          </div>
        </div>
      )}
    </div>
  );
}
