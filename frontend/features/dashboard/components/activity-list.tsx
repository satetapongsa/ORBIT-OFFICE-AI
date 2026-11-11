import { AlertTriangle, CircleDot } from "lucide-react";

import { actionLabel, isWarningAction } from "@/features/dashboard/labels";
import { formatDateTime, formatRelative } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { ActivityItem } from "@/services/dashboard";

interface ActivityListProps {
  items: ActivityItem[];
  /** Show who performed each action (organisation feed). */
  showActor?: boolean;
  /** The signed-in user's id, rendered as "คุณ" instead of their name. */
  selfId?: string;
  timeZone?: string;
  emptyText: string;
}

export function ActivityList({
  items,
  showActor = false,
  selfId,
  timeZone,
  emptyText,
}: ActivityListProps) {
  if (items.length === 0) {
    return <p className="text-muted-foreground py-6 text-center text-sm">{emptyText}</p>;
  }
  return (
    <ol className="space-y-3">
      {items.map((item) => {
        const warning = isWarningAction(item.action);
        const Icon = warning ? AlertTriangle : CircleDot;
        const actor = item.actor
          ? item.actor.id === selfId
            ? "คุณ"
            : item.actor.display_name
          : "ไม่ทราบผู้ใช้";
        return (
          <li key={item.id} className="flex gap-3 text-sm" data-testid="activity-item">
            <Icon
              className={cn(
                "mt-0.5 size-4 shrink-0",
                warning ? "text-amber-600" : "text-muted-foreground",
              )}
              aria-hidden
            />
            <div className="min-w-0 flex-1">
              <p className="truncate">
                {warning ? <span className="sr-only">คำเตือน: </span> : null}
                {actionLabel(item.action)}
                {showActor || (item.actor && item.actor.id !== selfId) ? (
                  <span className="text-muted-foreground"> · {actor}</span>
                ) : null}
              </p>
              <time
                dateTime={item.occurred_at}
                title={formatDateTime(item.occurred_at, timeZone)}
                className="text-muted-foreground text-xs"
              >
                {formatRelative(item.occurred_at)}
              </time>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
