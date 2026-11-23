import {
  Bell,
  CalendarDays,
  Megaphone,
  Plane,
  FileText,
  Headset,
  ListChecks,
  ShieldAlert,
  UserCog,
  type LucideIcon,
} from "lucide-react";

import type { NotificationType } from "@/services/notifications";

export const NOTIFICATION_TYPES: Record<NotificationType, { label: string; icon: LucideIcon }> = {
  SECURITY: { label: "ความปลอดภัย", icon: ShieldAlert },
  ACCOUNT: { label: "บัญชีผู้ใช้", icon: UserCog },
  SYSTEM: { label: "ระบบ", icon: Bell },
  DOCUMENT: { label: "เอกสาร", icon: FileText },
  TASK: { label: "งาน", icon: ListChecks },
  TICKET: { label: "แจ้งปัญหาไอที", icon: Headset },
  ANNOUNCEMENT: { label: "ประกาศบริษัท", icon: Megaphone },
  LEAVE: { label: "การลา", icon: Plane },
  MEETING: { label: "นัดประชุม", icon: CalendarDays },
};
