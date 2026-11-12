"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, MailWarning } from "lucide-react";
import { toast } from "sonner";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { NOTIFICATION_TYPES } from "@/features/notifications/labels";
import { ApiError } from "@/services/api-client";
import {
  getEmailPreferences,
  notificationQueryKeys,
  setEmailPreferences,
  type NotificationType,
} from "@/services/notifications";

/** Per-type choice of whether notifications are also sent by e-mail. */
export function EmailPreferencesCard() {
  const client = useQueryClient();
  const prefs = useQuery({
    queryKey: notificationQueryKeys.preferences,
    queryFn: ({ signal }) => getEmailPreferences(signal),
  });
  const save = useMutation({
    mutationFn: (item: { type: NotificationType; email_enabled: boolean }) =>
      setEmailPreferences([item]),
    onSuccess: (data) => {
      client.setQueryData(notificationQueryKeys.preferences, data);
      toast.success("บันทึกการตั้งค่าอีเมลแล้ว");
    },
    onError: (error) =>
      toast.error(error instanceof ApiError ? error.message : "บันทึกการตั้งค่าไม่สำเร็จ"),
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>การแจ้งเตือนทางอีเมล</CardTitle>
        <CardDescription>
          เลือกประเภทการแจ้งเตือนที่ต้องการให้ส่งอีเมลถึงคุณด้วย (การแจ้งเตือนในระบบยังแสดงตามปกติ)
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {prefs.isPending ? (
          <div className="space-y-2" aria-label="กำลังโหลด">
            <Skeleton className="h-5 w-48" />
            <Skeleton className="h-5 w-40" />
            <Skeleton className="h-5 w-44" />
          </div>
        ) : prefs.isError ? (
          <p className="text-destructive text-sm">โหลดการตั้งค่าไม่สำเร็จ</p>
        ) : (
          <>
            {!prefs.data.email_available && (
              <Alert>
                <MailWarning aria-hidden />
                <AlertDescription>
                  ระบบยังไม่ได้ตั้งค่าเซิร์ฟเวอร์อีเมล ตัวเลือกจะมีผลเมื่อผู้ดูแลระบบเปิดใช้งาน
                </AlertDescription>
              </Alert>
            )}
            <fieldset className="space-y-2.5" disabled={save.isPending}>
              <legend className="sr-only">ประเภทที่ส่งอีเมล</legend>
              {prefs.data.items.map((item) => (
                <label key={item.type} className="flex items-center gap-2.5 text-sm">
                  <input
                    type="checkbox"
                    className="size-4"
                    checked={item.email_enabled}
                    onChange={(e) =>
                      save.mutate({ type: item.type, email_enabled: e.target.checked })
                    }
                  />
                  {NOTIFICATION_TYPES[item.type].label}
                  {save.isPending && save.variables?.type === item.type && (
                    <Loader2 className="size-3.5 animate-spin" aria-label="กำลังบันทึก" />
                  )}
                </label>
              ))}
            </fieldset>
          </>
        )}
      </CardContent>
    </Card>
  );
}
