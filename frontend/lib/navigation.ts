import {
  BarChart3,
  Bell,
  Bot,
  FileText,
  Headset,
  LayoutDashboard,
  ListChecks,
  type LucideIcon,
  Settings,
  Activity,
  Users,
} from "lucide-react";

export interface NavItem {
  /** Stable key, also used in tests. */
  key: string;
  label: string;
  href: string;
  icon: LucideIcon;
  /**
   * Backend permission required to see this item (enforced by the backend; the
   * shell hides items the user lacks from Phase 2 onward). `null` = any signed-in user.
   */
  permission: string | null;
  /** Phase in which the module becomes functional. Items are disabled until then. */
  phase: number;
}

/** Development phase that is currently implemented (see docs/PROJECT_STATUS.md). */
export const CURRENT_PHASE = 1;

export const MAIN_NAV: NavItem[] = [
  {
    key: "dashboard",
    label: "แดชบอร์ด",
    href: "/dashboard",
    icon: LayoutDashboard,
    permission: null,
    phase: 3,
  },
  {
    key: "assistant",
    label: "ผู้ช่วย AI",
    href: "/assistant",
    icon: Bot,
    permission: "ai:chat",
    phase: 6,
  },
  {
    key: "documents",
    label: "ศูนย์เอกสาร",
    href: "/documents",
    icon: FileText,
    permission: "documents:read",
    phase: 4,
  },
  {
    key: "tasks",
    label: "จัดการงาน",
    href: "/tasks",
    icon: ListChecks,
    permission: "tasks:read_own",
    phase: 5,
  },
  {
    key: "employees",
    label: "ศูนย์พนักงาน",
    href: "/employees",
    icon: Users,
    permission: "employees:read_directory",
    phase: 5,
  },
  {
    key: "helpdesk",
    label: "แจ้งปัญหาไอที",
    href: "/helpdesk",
    icon: Headset,
    permission: "tickets:create",
    phase: 8,
  },
  {
    key: "analytics",
    label: "รายงานและการวิเคราะห์",
    href: "/analytics",
    icon: BarChart3,
    permission: "analytics:read_own",
    phase: 8,
  },
  {
    key: "notifications",
    label: "การแจ้งเตือน",
    href: "/notifications",
    icon: Bell,
    permission: null,
    phase: 8,
  },
];

export const SECONDARY_NAV: NavItem[] = [
  {
    key: "system-status",
    label: "สถานะระบบ",
    href: "/",
    icon: Activity,
    permission: null,
    phase: 1,
  },
  {
    key: "settings",
    label: "ตั้งค่า",
    href: "/settings",
    icon: Settings,
    permission: "system:configure",
    phase: 2,
  },
];

export function isNavItemAvailable(item: NavItem, currentPhase: number = CURRENT_PHASE): boolean {
  return item.phase <= currentPhase;
}

export function isNavItemActive(item: NavItem, pathname: string): boolean {
  if (item.href === "/") return pathname === "/";
  return pathname === item.href || pathname.startsWith(`${item.href}/`);
}
