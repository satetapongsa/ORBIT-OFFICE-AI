import { Brand } from "@/components/layout/brand";
import { SidebarNav } from "@/components/layout/sidebar-nav";

/** Desktop sidebar (hidden below the `lg` breakpoint; see MobileNav). */
export function AppSidebar() {
  return (
    <aside className="bg-sidebar fixed inset-y-0 left-0 z-30 hidden w-64 flex-col border-r lg:flex">
      <div className="flex h-16 items-center border-b px-5">
        <Brand />
      </div>
      <SidebarNav />
      <div className="text-muted-foreground border-t px-5 py-3 text-[11px]">
        เวอร์ชันพัฒนา 0.1.0
      </div>
    </aside>
  );
}
