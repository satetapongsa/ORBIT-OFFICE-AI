"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { Badge } from "@/components/ui/badge";
import { useSession } from "@/features/auth/hooks/use-session";
import { cn } from "@/lib/utils";
import {
  MAIN_NAV,
  SECONDARY_NAV,
  isNavItemActive,
  isNavItemAvailable,
  isNavItemPermitted,
  type NavItem,
} from "@/lib/navigation";

interface SidebarNavProps {
  /** Called after a link is chosen (closes the mobile drawer). */
  onNavigate?: () => void;
}

function NavEntry({
  item,
  pathname,
  onNavigate,
}: {
  item: NavItem;
  pathname: string;
  onNavigate?: () => void;
}) {
  const Icon = item.icon;
  const base =
    "group flex h-9 items-center gap-3 rounded-lg px-3 text-sm font-medium transition-colors outline-none focus-visible:ring-3 focus-visible:ring-sidebar-ring/50";

  if (!isNavItemAvailable(item)) {
    return (
      <span
        aria-disabled="true"
        data-testid={`nav-${item.key}`}
        title="อยู่ระหว่างการพัฒนา"
        className={cn(base, "text-muted-foreground/70 cursor-not-allowed")}
      >
        <Icon className="size-4 shrink-0" aria-hidden />
        <span className="truncate">{item.label}</span>
        <Badge variant="outline" className="ml-auto h-5 px-1.5 text-[10px] font-normal">
          เร็วๆ นี้
        </Badge>
      </span>
    );
  }

  const active = isNavItemActive(item, pathname);
  return (
    <Link
      href={item.href}
      data-testid={`nav-${item.key}`}
      aria-current={active ? "page" : undefined}
      onClick={onNavigate}
      className={cn(
        base,
        active
          ? "bg-sidebar-accent text-sidebar-accent-foreground"
          : "text-sidebar-foreground/80 hover:bg-sidebar-accent/60 hover:text-sidebar-foreground",
      )}
    >
      <Icon className="size-4 shrink-0" aria-hidden />
      <span className="truncate">{item.label}</span>
    </Link>
  );
}

export function SidebarNav({ onNavigate }: SidebarNavProps) {
  const pathname = usePathname() ?? "/";
  const { has } = useSession();
  // Cosmetic only: the backend independently rejects requests the user is not allowed to make.
  const main = MAIN_NAV.filter((item) => isNavItemPermitted(item, has));
  const secondary = SECONDARY_NAV.filter((item) => isNavItemPermitted(item, has));
  return (
    <nav aria-label="เมนูหลัก" className="flex flex-1 flex-col gap-6 overflow-y-auto px-3 py-4">
      <div className="flex flex-col gap-1">
        <p className="text-muted-foreground px-3 pb-1 text-xs font-medium tracking-wide">
          เมนูหลัก
        </p>
        {main.map((item) => (
          <NavEntry key={item.key} item={item} pathname={pathname} onNavigate={onNavigate} />
        ))}
      </div>
      <div className="flex flex-col gap-1">
        <p className="text-muted-foreground px-3 pb-1 text-xs font-medium tracking-wide">ระบบ</p>
        {secondary.map((item) => (
          <NavEntry key={item.key} item={item} pathname={pathname} onNavigate={onNavigate} />
        ))}
      </div>
    </nav>
  );
}
