"use client";

import { Menu } from "lucide-react";
import { useState } from "react";

import { Brand } from "@/components/layout/brand";
import { SidebarNav } from "@/components/layout/sidebar-nav";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";

export function MobileNav() {
  const [open, setOpen] = useState(false);
  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button variant="ghost" size="icon" className="lg:hidden" aria-label="เปิดเมนู">
          <Menu />
        </Button>
      </SheetTrigger>
      <SheetContent side="left" className="bg-sidebar w-72 gap-0 p-0">
        <SheetHeader className="h-16 justify-center border-b px-5">
          <SheetTitle className="sr-only">เมนูนำทาง</SheetTitle>
          <Brand />
        </SheetHeader>
        <SidebarNav onNavigate={() => setOpen(false)} />
      </SheetContent>
    </Sheet>
  );
}
