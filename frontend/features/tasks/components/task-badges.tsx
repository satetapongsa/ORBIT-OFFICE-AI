import {
  ArrowDown,
  ArrowUp,
  CalendarClock,
  CheckCircle2,
  Circle,
  CircleDashed,
  Eye,
  Flame,
  Minus,
  XCircle,
} from "lucide-react";

import { TASK_PRIORITY_LABELS, TASK_STATUS_LABELS, formatDue } from "@/features/tasks/labels";
import { cn } from "@/lib/utils";
import type { TaskPriority, TaskStatus } from "@/services/tasks";

const PILL =
  "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap";

const STATUS_STYLES: Record<TaskStatus, { icon: typeof Circle; className: string }> = {
  TODO: { icon: Circle, className: "bg-muted text-muted-foreground" },
  IN_PROGRESS: { icon: CircleDashed, className: "bg-blue-50 text-blue-700" },
  REVIEW: { icon: Eye, className: "bg-violet-50 text-violet-700" },
  COMPLETED: { icon: CheckCircle2, className: "bg-emerald-50 text-emerald-700" },
  CANCELLED: { icon: XCircle, className: "bg-zinc-100 text-zinc-600 line-through" },
};

const PRIORITY_STYLES: Record<TaskPriority, { icon: typeof Circle; className: string }> = {
  LOW: { icon: ArrowDown, className: "text-muted-foreground" },
  MEDIUM: { icon: Minus, className: "text-foreground" },
  HIGH: { icon: ArrowUp, className: "text-amber-700" },
  URGENT: { icon: Flame, className: "text-red-700" },
};

/** Status carries an icon and a label, never colour alone. */
export function TaskStatusBadge({ status }: { status: TaskStatus }) {
  const { icon: Icon, className } = STATUS_STYLES[status];
  return (
    <span data-testid="task-status" className={cn(PILL, className)}>
      <Icon className="size-3" aria-hidden />
      {TASK_STATUS_LABELS[status]}
    </span>
  );
}

export function TaskPriorityLabel({ priority }: { priority: TaskPriority }) {
  const { icon: Icon, className } = PRIORITY_STYLES[priority];
  return (
    <span className={cn("inline-flex items-center gap-1 text-xs font-medium", className)}>
      <Icon className="size-3.5" aria-hidden />
      {TASK_PRIORITY_LABELS[priority]}
    </span>
  );
}

export function DueLabel({ dueAt, overdue }: { dueAt: string | null; overdue: boolean }) {
  if (!dueAt) return <span className="text-muted-foreground text-xs">ไม่มีกำหนดส่ง</span>;
  return (
    <span
      data-testid="task-due"
      className={cn(
        "inline-flex items-center gap-1 text-xs",
        overdue ? "font-semibold text-red-700" : "text-muted-foreground",
      )}
    >
      <CalendarClock className="size-3.5" aria-hidden />
      {overdue ? "เลยกำหนด " : "ส่ง "}
      {formatDue(dueAt)}
    </span>
  );
}
