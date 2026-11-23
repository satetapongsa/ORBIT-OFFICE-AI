"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight, Megaphone, Pin } from "lucide-react";
import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatRelative } from "@/lib/format";
import {
  announcementQueryKeys,
  getAnnouncementUnread,
  listAnnouncements,
} from "@/services/announcements";

/** Unread announcements, next to "ประกาศ" in the menu. */
export function AnnouncementUnreadBadge() {
  const unread = useQuery({
    queryKey: announcementQueryKeys.unread,
    queryFn: ({ signal }) => getAnnouncementUnread(signal),
    refetchInterval: 120_000,
    staleTime: 30_000,
  });
  const count = unread.data?.unread_count ?? 0;
  if (!count) return null;
  return (
    <Badge
      className="ml-auto h-5 min-w-5 justify-center px-1.5 text-[11px]"
      aria-label={`ประกาศใหม่ ${count} รายการ`}
    >
      {count > 99 ? "99+" : count}
    </Badge>
  );
}

/** Dashboard card: the three newest announcements (pinned first). */
export function LatestAnnouncementsCard() {
  const list = useQuery({
    queryKey: announcementQueryKeys.list(false),
    queryFn: ({ signal }) => listAnnouncements(false, signal),
  });
  const items = (list.data?.items ?? []).slice(0, 3);
  if (list.isPending || items.length === 0) return null;
  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-3">
        <div className="space-y-1">
          <CardTitle className="flex items-center gap-2">
            <Megaphone className="text-primary size-4" aria-hidden />
            ประกาศล่าสุด
          </CardTitle>
          <CardDescription>
            {list.data?.unread_count
              ? `ยังไม่อ่าน ${list.data.unread_count} รายการ`
              : "อ่านครบแล้ว"}
          </CardDescription>
        </div>
        <Button asChild variant="ghost" size="sm">
          <Link href="/announcements">
            ดูทั้งหมด
            <ArrowRight aria-hidden />
          </Link>
        </Button>
      </CardHeader>
      <CardContent>
        <ul className="divide-y">
          {items.map((a) => (
            <li key={a.id}>
              <Link
                href={`/announcements?id=${a.id}`}
                className="hover:bg-accent/50 -mx-2 flex items-start gap-3 rounded-lg px-2 py-2.5"
              >
                {a.important ? (
                  <AlertTriangle className="mt-0.5 size-4 shrink-0 text-amber-600" aria-hidden />
                ) : (
                  <Megaphone className="text-muted-foreground mt-0.5 size-4 shrink-0" aria-hidden />
                )}
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-1.5">
                    {!a.is_read ? (
                      <span
                        className="bg-primary size-2 shrink-0 rounded-full"
                        aria-label="ยังไม่อ่าน"
                      />
                    ) : null}
                    <span className="truncate text-sm font-medium">{a.title}</span>
                    {a.pinned ? (
                      <Pin className="text-muted-foreground size-3 shrink-0" aria-hidden />
                    ) : null}
                  </span>
                  <span className="text-muted-foreground line-clamp-1 text-xs">{a.body}</span>
                </span>
                <span className="text-muted-foreground shrink-0 text-xs">
                  {formatRelative(a.published_at)}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
