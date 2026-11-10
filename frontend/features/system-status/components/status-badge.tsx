import { CheckCircle2, CircleDashed, Settings2, XCircle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { STATUS_LABELS } from "@/features/system-status/labels";
import type { ComponentStatus } from "@/services/health";

const STYLES: Record<ComponentStatus, { className: string; Icon: typeof CheckCircle2 }> = {
  ok: { className: "bg-emerald-50 text-emerald-700 border-emerald-200", Icon: CheckCircle2 },
  error: { className: "bg-red-50 text-red-700 border-red-200", Icon: XCircle },
  configured: { className: "bg-sky-50 text-sky-700 border-sky-200", Icon: Settings2 },
  not_configured: { className: "bg-muted text-muted-foreground border-border", Icon: CircleDashed },
};

export function StatusBadge({ status }: { status: ComponentStatus }) {
  const { className, Icon } = STYLES[status];
  return (
    <Badge variant="outline" className={cn("gap-1 font-medium", className)}>
      <Icon className="size-3.5" aria-hidden />
      {STATUS_LABELS[status]}
    </Badge>
  );
}
