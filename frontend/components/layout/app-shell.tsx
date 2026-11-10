import type { ReactNode } from "react";

import { AppHeader } from "@/components/layout/app-header";
import { AppSidebar } from "@/components/layout/app-sidebar";

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen">
      <a
        href="#main-content"
        className="focus:bg-background sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-50 focus:rounded-md focus:px-3 focus:py-2 focus:shadow"
      >
        ข้ามไปยังเนื้อหาหลัก
      </a>
      <AppSidebar />
      <div className="flex min-h-screen flex-col lg:pl-64">
        <AppHeader />
        <main id="main-content" className="flex-1 px-4 py-6 sm:px-6 lg:px-8">
          <div className="mx-auto w-full max-w-7xl">{children}</div>
        </main>
      </div>
    </div>
  );
}
