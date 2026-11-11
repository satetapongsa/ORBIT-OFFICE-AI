"use client";

import { Check } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { useMarkNotificationRead } from "@/features/notifications/hooks/use-notifications";
import { NOTIFICATION_TYPES } from "@/features/notifications/labels";
import { formatDateTime, formatRelative } from "@/lib/format";
import { cn } from "@/lib/utils";
import { safeRedirectPath } from "@/services/auth";
import type { AppNotification } from "@/services/notifications";

interface NotificationItemProps {
  notification: AppNotification;
  /** Compact rows (header menu, dashboard preview) clamp the body to one line. */
  compact?: boolean;
  /** Show a separate "mark as read" button (full notifications page). */
  showMarkRead?: boolean;
  onNavigate?: () => void;
}

export function NotificationItem({
  notification,
  compact = false,
  showMarkRead = false,
  onNavigate,
}: NotificationItemProps) {
  const markRead = useMarkNotificationRead();
  const unread = notification.read_at === null;
  const { icon: Icon, label } = NOTIFICATION_TYPES[notification.type];
  // Links come from the backend and are relative by contract; re-check before rendering.
  const href = notification.link_url ? safeRedirectPath(notification.link_url, "") : "";

  const open = () => {
    if (unread) markRead.mutate(notification.id);
    onNavigate?.();
  };

  const content = (
    <>
      <span
        className={cn(
          "mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full",
          notification.type === "SECURITY"
            ? "bg-amber-100 text-amber-700"
            : "bg-primary/10 text-primary",
        )}
      >
        <Icon className="size-4" aria-hidden />
        <span className="sr-only">{label}</span>
      </span>
      <span className="min-w-0 flex-1 space-y-0.5 text-left">
        <span className={cn("block text-sm", unread ? "font-semibold" : "font-medium")}>
          {unread ? <span className="sr-only">ยังไม่อ่าน: </span> : null}
          {notification.title}
        </span>
        {notification.body ? (
          <span className={cn("text-muted-foreground block text-xs", compact && "line-clamp-1")}>
            {notification.body}
          </span>
        ) : null}
        <time
          dateTime={notification.created_at}
          title={formatDateTime(notification.created_at)}
          className="text-muted-foreground block text-xs"
        >
          {formatRelative(notification.created_at)}
        </time>
      </span>
      {unread ? (
        <span className="bg-primary mt-1.5 size-2 shrink-0 rounded-full" aria-hidden />
      ) : null}
    </>
  );

  const rowClass = cn(
    "hover:bg-muted/60 focus-visible:ring-ring/50 flex w-full gap-3 rounded-lg p-2.5 outline-none focus-visible:ring-2",
    unread && "bg-primary/5",
  );

  return (
    <div className="flex items-start gap-1" data-testid="notification-item">
      {href ? (
        <Link href={href} className={rowClass} onClick={open}>
          {content}
        </Link>
      ) : (
        <button type="button" className={rowClass} onClick={open}>
          {content}
        </button>
      )}
      {showMarkRead && unread ? (
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="mt-1.5 shrink-0"
          aria-label={`ทำเครื่องหมายว่าอ่านแล้ว: ${notification.title}`}
          disabled={markRead.isPending}
          onClick={() => markRead.mutate(notification.id)}
        >
          <Check aria-hidden />
        </Button>
      ) : null}
    </div>
  );
}
