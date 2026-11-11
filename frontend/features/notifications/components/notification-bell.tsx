"use client";

import { Bell, CheckCheck } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { NotificationItem } from "@/features/notifications/components/notification-item";
import {
  useMarkAllNotificationsRead,
  useNotificationList,
  useUnreadCount,
} from "@/features/notifications/hooks/use-notifications";

const PREVIEW_SIZE = 5;

export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const unread = useUnreadCount();
  // The list is fetched only while the menu is open.
  const list = useNotificationList({ page: 1, pageSize: PREVIEW_SIZE }, open);
  const markAll = useMarkAllNotificationsRead();
  const count = unread.data ?? 0;
  const label = count > 0 ? `การแจ้งเตือน (${count} รายการยังไม่อ่าน)` : "การแจ้งเตือน";

  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className="relative" aria-label={label}>
          <Bell aria-hidden />
          {count > 0 ? (
            <Badge
              data-testid="unread-badge"
              className="absolute -top-0.5 -right-0.5 h-4 min-w-4 rounded-full px-1 text-[10px] tabular-nums"
            >
              {count > 99 ? "99+" : count}
            </Badge>
          ) : null}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-[min(22rem,calc(100vw-2rem))] p-0">
        <div className="flex items-center justify-between gap-2 px-3 pt-2">
          <DropdownMenuLabel className="px-0">การแจ้งเตือน</DropdownMenuLabel>
          <Button
            variant="ghost"
            size="sm"
            className="h-7 text-xs"
            disabled={count === 0 || markAll.isPending}
            onClick={() => markAll.mutate()}
          >
            <CheckCheck aria-hidden />
            อ่านทั้งหมด
          </Button>
        </div>
        <DropdownMenuSeparator className="my-0" />
        <div className="max-h-96 overflow-y-auto p-1.5">
          {list.isPending ? (
            <div className="space-y-2 p-1.5">
              {Array.from({ length: 3 }, (_, i) => (
                <Skeleton key={i} className="h-14 w-full" />
              ))}
            </div>
          ) : list.isError ? (
            <p className="text-muted-foreground p-4 text-center text-sm">
              ไม่สามารถโหลดการแจ้งเตือนได้
            </p>
          ) : list.data.items.length === 0 ? (
            <p className="text-muted-foreground p-6 text-center text-sm">ยังไม่มีการแจ้งเตือน</p>
          ) : (
            list.data.items.map((n) => (
              <NotificationItem
                key={n.id}
                notification={n}
                compact
                onNavigate={() => setOpen(false)}
              />
            ))
          )}
        </div>
        <DropdownMenuSeparator className="my-0" />
        <div className="p-1.5">
          <Button asChild variant="ghost" size="sm" className="w-full">
            <Link href="/notifications" onClick={() => setOpen(false)}>
              ดูการแจ้งเตือนทั้งหมด
            </Link>
          </Button>
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
