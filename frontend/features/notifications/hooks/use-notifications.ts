"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { dashboardQueryKeys } from "@/services/dashboard";
import {
  getUnreadCount,
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  notificationQueryKeys,
  type NotificationListParams,
} from "@/services/notifications";

const UNREAD_POLL_MS = 60_000;

export function useUnreadCount() {
  return useQuery({
    queryKey: notificationQueryKeys.unreadCount,
    queryFn: ({ signal }) => getUnreadCount(signal),
    refetchInterval: UNREAD_POLL_MS,
    staleTime: 15_000,
  });
}

export function useNotificationList(params: NotificationListParams, enabled = true) {
  return useQuery({
    queryKey: notificationQueryKeys.list(params),
    queryFn: ({ signal }) => listNotifications(params, signal),
    enabled,
    staleTime: 15_000,
  });
}

/** Read-state changes refresh every notification view and the dashboard preview. */
function useInvalidateNotifications() {
  const client = useQueryClient();
  return () =>
    Promise.all([
      client.invalidateQueries({ queryKey: notificationQueryKeys.all }),
      client.invalidateQueries({ queryKey: dashboardQueryKeys.summary }),
    ]);
}

export function useMarkNotificationRead() {
  const invalidate = useInvalidateNotifications();
  return useMutation({
    mutationFn: markNotificationRead,
    onSuccess: invalidate,
    onError: () => toast.error("ไม่สามารถอัปเดตการแจ้งเตือนได้ กรุณาลองใหม่"),
  });
}

export function useMarkAllNotificationsRead() {
  const invalidate = useInvalidateNotifications();
  return useMutation({
    mutationFn: markAllNotificationsRead,
    onSuccess: async (result) => {
      await invalidate();
      if (result.updated > 0) toast.success("ทำเครื่องหมายว่าอ่านแล้วทั้งหมด");
    },
    onError: () => toast.error("ไม่สามารถอัปเดตการแจ้งเตือนได้ กรุณาลองใหม่"),
  });
}
