import { Sparkles } from "lucide-react";
import Link from "next/link";

export function Brand() {
  return (
    <Link
      href="/dashboard"
      className="focus-visible:ring-ring/50 flex items-center gap-2.5 rounded-lg outline-none focus-visible:ring-3"
    >
      <span className="bg-primary text-primary-foreground flex size-8 items-center justify-center rounded-lg">
        <Sparkles className="size-4" aria-hidden />
      </span>
      <span className="flex flex-col leading-tight">
        <span className="text-sm font-semibold tracking-wide">ORBIT OFFICE AI</span>
        <span className="text-muted-foreground text-[11px]">ระบบบริหารงานสำนักงาน</span>
      </span>
    </Link>
  );
}
