import { AlertCircle, CheckCircle2, Clock, Loader2 } from "lucide-react";

import { PROCESSING_LABELS } from "@/features/documents/labels";
import { cn } from "@/lib/utils";
import type { ProcessingStatus } from "@/services/documents";

const STYLES: Record<ProcessingStatus, { icon: typeof Clock; className: string }> = {
  PENDING: { icon: Clock, className: "bg-muted text-muted-foreground" },
  PROCESSING: { icon: Loader2, className: "bg-blue-50 text-blue-700" },
  READY: { icon: CheckCircle2, className: "bg-emerald-50 text-emerald-700" },
  FAILED: { icon: AlertCircle, className: "bg-red-50 text-red-700" },
};

/** Status always carries an icon and a label, never colour alone. */
export function ProcessingBadge({ status }: { status: ProcessingStatus }) {
  const { icon: Icon, className } = STYLES[status];
  return (
    <span
      data-testid="processing-badge"
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap",
        className,
      )}
    >
      <Icon className={cn("size-3", status === "PROCESSING" && "animate-spin")} aria-hidden />
      {PROCESSING_LABELS[status]}
    </span>
  );
}
