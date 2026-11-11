import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { Card, CardContent } from "@/components/ui/card";
import { numberFormat } from "@/lib/format";

interface StatCardProps {
  label: string;
  value: number;
  icon: LucideIcon;
  /** Short supporting text under the number. */
  hint?: ReactNode;
  testId?: string;
}

/** A headline number: the label names it, the value is the largest text on the card. */
export function StatCard({ label, value, icon: Icon, hint, testId }: StatCardProps) {
  return (
    <Card className="gap-0 py-4" data-testid={testId}>
      <CardContent className="space-y-2 px-3 sm:px-4">
        <div className="flex items-center justify-between gap-2">
          <p className="text-muted-foreground text-xs sm:text-sm">{label}</p>
          <span className="bg-primary/10 text-primary hidden size-8 shrink-0 items-center justify-center rounded-lg sm:flex">
            <Icon className="size-4" aria-hidden />
          </span>
        </div>
        <p className="text-2xl font-semibold tracking-tight tabular-nums sm:text-3xl">
          {numberFormat.format(value)}
        </p>
        {hint ? <p className="text-muted-foreground text-xs">{hint}</p> : null}
      </CardContent>
    </Card>
  );
}
