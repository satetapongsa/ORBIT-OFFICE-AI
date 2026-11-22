"use client";

import { useChatRealtime } from "@/features/chat/hooks/use-chat-realtime";

/** Mounted once in the signed-in layout; keeps chat updates live on every page. */
export function ChatRealtime() {
  useChatRealtime();
  return null;
}
