import { MobileNav } from "@/components/layout/mobile-nav";
import { SystemStatusIndicator } from "@/features/system-status/components/system-status-indicator";

export function AppHeader() {
  return (
    <header className="bg-background/85 supports-[backdrop-filter]:bg-background/70 sticky top-0 z-20 flex h-16 items-center gap-3 border-b px-4 backdrop-blur sm:px-6">
      <MobileNav />
      <div className="flex-1" />
      <SystemStatusIndicator />
    </header>
  );
}
