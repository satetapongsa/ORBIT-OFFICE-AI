"use client";

import { BellOff, CheckCheck, ChevronLeft, ChevronRight } from "lucide-react";
import { useState } from "react";

import { EmptyState } from "@/components/common/empty-state";
import { ErrorState } from "@/components/common/error-state";
import { PageHeader } from "@/components/common/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { NotificationItem } from "@/features/notifications/components/notification-item";
import {
  useMarkAllNotificationsRead,
  useNotificationList,
} from "@/features/notifications/hooks/use-notifications";
import { cn } from "@/lib/utils";
import { ApiError } from "@/services/api-client";

const PAGE_SIZE = 20;
const FILTERS = [
  { key: "all", label: "ทั้งหมด", unreadOnly: false },
  { key: "unread", label: "ยังไม่อ่าน", unreadOnly: true },
] as const;

export function NotificationsView() {
  const [filter, setFilter] = useState<(typeof FILTERS)[number]["key"]>("all");
  const [page, setPage] = useState(1);
  const unreadOnly = filter === "unread";
  const list = useNotificationList({ page, pageSize: PAGE_SIZE, unreadOnly });
  const markAll = useMarkAllNotificationsRead();
  const unreadCount = list.data?.unread_count ?? 0;
  const totalPages = list.data ? Math.max(1, Math.ceil(list.data.total / PAGE_SIZE)) : 1;

  return (
    <>
      <PageHeader
        title="การแจ้งเตือน"
        description="แจ้งเตือนเกี่ยวกับบัญชีและความปลอดภัยของคุณ เห็นได้เฉพาะเจ้าของบัญชีเท่านั้น"
        actions={
          <Button
            variant="outline"
            size="sm"
            disabled={unreadCount === 0 || markAll.isPending}
            onClick={() => markAll.mutate()}
          >
            <CheckCheck aria-hidden />
            อ่านทั้งหมด
          </Button>
        }
      />

      <div role="group" aria-label="ตัวกรอง" className="bg-muted mb-4 inline-flex rounded-lg p-1">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            type="button"
            aria-pressed={filter === f.key}
            onClick={() => {
              setFilter(f.key);
              setPage(1);
            }}
            className={cn(
              "focus-visible:ring-ring/50 rounded-md px-3 py-1 text-sm font-medium outline-none focus-visible:ring-2",
              filter === f.key
                ? "bg-background shadow-sm"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {f.label}
            {f.unreadOnly && unreadCount > 0 ? ` (${unreadCount})` : ""}
          </button>
        ))}
      </div>

      {list.isPending ? (
        <Card>
          <CardContent className="space-y-3">
            {Array.from({ length: 4 }, (_, i) => (
              <Skeleton key={i} className="h-16 w-full" />
            ))}
          </CardContent>
        </Card>
      ) : list.isError ? (
        <ErrorState
          message={list.error.message}
          requestId={list.error instanceof ApiError ? list.error.requestId : null}
          onRetry={() => void list.refetch()}
          retrying={list.isFetching}
        />
      ) : list.data.items.length === 0 ? (
        <EmptyState
          icon={BellOff}
          title={unreadOnly ? "ไม่มีการแจ้งเตือนที่ยังไม่อ่าน" : "ยังไม่มีการแจ้งเตือน"}
          description="เมื่อมีการเปลี่ยนแปลงเกี่ยวกับบัญชีหรือความปลอดภัยของคุณ ระบบจะแจ้งที่นี่"
        />
      ) : (
        <Card className="py-2">
          <CardContent className="divide-y px-2">
            {list.data.items.map((n) => (
              <div key={n.id} className="py-1">
                <NotificationItem notification={n} showMarkRead />
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {list.data && totalPages > 1 ? (
        <nav aria-label="เลื่อนหน้า" className="mt-4 flex items-center justify-end gap-2 text-sm">
          <Button
            variant="outline"
            size="sm"
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
          >
            <ChevronLeft aria-hidden />
            ก่อนหน้า
          </Button>
          <span className="text-muted-foreground tabular-nums">
            หน้า {page} / {totalPages}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={page >= totalPages}
            onClick={() => setPage((p) => p + 1)}
          >
            ถัดไป
            <ChevronRight aria-hidden />
          </Button>
        </nav>
      ) : null}
    </>
  );
}
