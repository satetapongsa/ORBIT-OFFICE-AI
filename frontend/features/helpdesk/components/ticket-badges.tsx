import {
  CheckCircle2,
  Circle,
  CircleDashed,
  CircleHelp,
  CircleSlash,
  Lock,
  type LucideIcon,
} from "lucide-react";

import { TICKET_STATUS_LABELS } from "@/features/helpdesk/labels";
import { cn } from "@/lib/utils";
import type { TicketStatus } from "@/services/tickets";

const STYLES: Record<TicketStatus, { icon: LucideIcon; className: string }> = {
  OPEN: { icon: Circle, className: "bg-amber-50 text-amber-800" },
  IN_PROGRESS: { icon: CircleDashed, className: "bg-blue-50 text-blue-700" },
  WAITING_FOR_USER: { icon: CircleHelp, className: "bg-violet-50 text-violet-700" },
  RESOLVED: { icon: CheckCircle2, className: "bg-emerald-50 text-emerald-700" },
  CLOSED: { icon: Lock, className: "bg-muted text-muted-foreground" },
  CANCELLED: { icon: CircleSlash, className: "bg-zinc-100 text-zinc-600 line-through" },
};

/** Status carries an icon and a label, never colour alone. */
export function TicketStatusBadge({ status }: { status: TicketStatus }) {
  const { icon: Icon, className } = STYLES[status];
  return (
    <span
      data-testid="ticket-status"
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap",
        className,
      )}
    >
      <Icon className="size-3" aria-hidden />
      {TICKET_STATUS_LABELS[status]}
    </span>
  );
}
