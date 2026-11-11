import { Bell, FileText, ShieldAlert, UserCog, type LucideIcon } from "lucide-react";

import type { NotificationType } from "@/services/notifications";

export const NOTIFICATION_TYPES: Record<NotificationType, { label: string; icon: LucideIcon }> = {
  SECURITY: { label: "ความปลอดภัย", icon: ShieldAlert },
  ACCOUNT: { label: "บัญชีผู้ใช้", icon: UserCog },
  SYSTEM: { label: "ระบบ", icon: Bell },
  DOCUMENT: { label: "เอกสาร", icon: FileText },
};
