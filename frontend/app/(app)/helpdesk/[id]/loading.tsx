import { Skeleton } from "@/components/ui/skeleton";

/** Static shell for /helpdesk/[id] while the request-time segment streams in. */
export default function Loading() {
  return (
    <div className="space-y-6" aria-busy="true" aria-label="กำลังโหลดรายการแจ้งปัญหา">
      <Skeleton className="h-8 w-72" />
      <div className="grid gap-4 lg:grid-cols-3">
        <Skeleton className="h-80 rounded-xl lg:col-span-2" />
        <Skeleton className="h-80 rounded-xl" />
      </div>
    </div>
  );
}
