import { Skeleton } from "@/components/ui/skeleton";

/** Static shell for /employees/[id] while the request-time segment streams in. */
export default function Loading() {
  return (
    <div className="space-y-6" aria-busy="true" aria-label="กำลังโหลดข้อมูลพนักงาน">
      <Skeleton className="h-20 w-full max-w-xl" />
      <div className="grid gap-4 lg:grid-cols-3">
        <Skeleton className="h-72 rounded-xl lg:col-span-2" />
        <Skeleton className="h-72 rounded-xl" />
      </div>
    </div>
  );
}
