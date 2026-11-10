import { FileQuestion } from "lucide-react";
import Link from "next/link";

import { EmptyState } from "@/components/common/empty-state";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <main className="flex min-h-screen items-center justify-center p-6">
      <EmptyState
        icon={FileQuestion}
        title="ไม่พบหน้าที่คุณต้องการ"
        description="หน้านี้อาจถูกย้าย ถูกลบ หรือยังไม่เปิดให้ใช้งาน"
        action={
          <Button asChild variant="outline">
            <Link href="/">กลับหน้าหลัก</Link>
          </Button>
        }
      />
    </main>
  );
}
