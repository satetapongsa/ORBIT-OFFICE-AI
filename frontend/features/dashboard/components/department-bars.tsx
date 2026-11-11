import { numberFormat } from "@/lib/format";
import type { DashboardSummary } from "@/services/dashboard";

type Headcount = NonNullable<DashboardSummary["organization"]>["users_by_department"];

/** Horizontal bars, largest first; the value sits beside each bar in text ink. */
export function DepartmentBars({ rows }: { rows: Headcount }) {
  const max = Math.max(1, ...rows.map((r) => r.count));
  return (
    <ul className="space-y-3" aria-label="จำนวนพนักงานแยกตามแผนก">
      {rows.map((row) => {
        const name = row.department?.name ?? "ไม่ระบุแผนก";
        return (
          <li
            key={row.department?.id ?? "none"}
            className="grid grid-cols-[minmax(0,9rem)_1fr_auto] items-center gap-3 text-sm"
            data-testid={`headcount-${row.department?.code ?? "none"}`}
          >
            <span className="truncate" title={name}>
              {name}
            </span>
            <span className="bg-muted/60 h-2.5 overflow-hidden rounded-r-[4px]" aria-hidden>
              <span
                className="block h-full rounded-r-[4px]"
                style={{ width: `${(row.count / max) * 100}%`, backgroundColor: "var(--chart-1)" }}
              />
            </span>
            <span className="text-right tabular-nums">{numberFormat.format(row.count)} คน</span>
          </li>
        );
      })}
    </ul>
  );
}
