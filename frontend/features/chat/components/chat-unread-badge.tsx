"use client";

import { useQuery } from "@tanstack/react-query";

import { Badge } from "@/components/ui/badge";
import { chatQueryKeys, getChatUnread } from "@/services/chat";

const UNREAD_POLL_MS = 30_000;

/** Unread direct messages, shown next to "แชท" in the menu. */
export function ChatUnreadBadge() {
  const unread = useQuery({
    queryKey: chatQueryKeys.unread,
    queryFn: ({ signal }) => getChatUnread(signal),
    refetchInterval: UNREAD_POLL_MS,
    staleTime: 10_000,
  });
  const count = unread.data?.unread_total ?? 0;
  if (!count) return null;
  return (
    <Badge
      className="ml-auto h-5 min-w-5 justify-center px-1.5 text-[11px]"
      aria-label={`ข้อความใหม่ ${count} ข้อความ`}
    >
      {count > 99 ? "99+" : count}
    </Badge>
  );
}
