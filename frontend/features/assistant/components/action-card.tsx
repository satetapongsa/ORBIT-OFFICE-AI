"use client";

import { Check, CircleAlert, Clock, Loader2, ShieldQuestion, X } from "lucide-react";
import Link from "next/link";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { useDecideAction } from "@/features/assistant/hooks/use-assistant";
import { cn } from "@/lib/utils";
import type { ActionStatus, AiAction } from "@/services/ai";
import { ApiError } from "@/services/api-client";

const STATUS: Record<ActionStatus, { label: string; icon: typeof Check; className: string }> = {
  PENDING: { label: "รอการยืนยันจากคุณ", icon: ShieldQuestion, className: "text-amber-700" },
  EXECUTED: { label: "ดำเนินการแล้ว", icon: Check, className: "text-emerald-700" },
  REJECTED: {
    label: "ปฏิเสธแล้ว — ไม่มีการเปลี่ยนแปลง",
    icon: X,
    className: "text-muted-foreground",
  },
  FAILED: { label: "ดำเนินการไม่สำเร็จ", icon: CircleAlert, className: "text-red-700" },
  EXPIRED: { label: "หมดเวลายืนยัน", icon: Clock, className: "text-muted-foreground" },
};

function resultLink(action: AiAction): string | null {
  const link = action.result?.["link"];
  return typeof link === "string" && /^\/[a-z]/.test(link) ? link : null;
}

/** A change the assistant prepared. Nothing happens until the user presses "ยืนยัน". */
export function ActionCard({ action, sessionId }: { action: AiAction; sessionId: string | null }) {
  const decide = useDecideAction(sessionId);
  const { label, icon: Icon, className } = STATUS[action.status];
  const link = resultLink(action);
  const run = (confirm: boolean) =>
    decide.mutate(
      { id: action.id, confirm },
      {
        onSuccess: (result) => {
          if (result.status === "EXECUTED") toast.success("ดำเนินการเรียบร้อย");
          else if (result.status === "FAILED") toast.error(result.error ?? "ดำเนินการไม่สำเร็จ");
        },
        onError: (error) =>
          toast.error(error instanceof ApiError ? error.message : "ดำเนินการไม่สำเร็จ"),
      },
    );

  return (
    <div
      data-testid="action-card"
      className={cn(
        "rounded-lg border p-3 text-sm",
        action.status === "PENDING" ? "border-amber-300 bg-amber-50/60" : "bg-muted/30",
      )}
    >
      <p className="font-medium">{action.summary}</p>
      <p className={cn("mt-1 inline-flex items-center gap-1 text-xs font-medium", className)}>
        <Icon className="size-3.5" aria-hidden />
        {label}
      </p>
      {action.status === "FAILED" && action.error ? (
        <p className="mt-1 text-xs text-red-700">{action.error}</p>
      ) : null}
      {action.status === "PENDING" ? (
        <div className="mt-3 flex flex-wrap gap-2">
          <Button size="sm" disabled={decide.isPending} onClick={() => run(true)}>
            {decide.isPending ? (
              <Loader2 className="animate-spin" aria-hidden />
            ) : (
              <Check aria-hidden />
            )}
            ยืนยัน
          </Button>
          <Button
            size="sm"
            variant="outline"
            disabled={decide.isPending}
            onClick={() => run(false)}
          >
            <X aria-hidden />
            ปฏิเสธ
          </Button>
        </div>
      ) : null}
      {link ? (
        <Button asChild size="sm" variant="link" className="mt-1 h-auto px-0">
          <Link href={link}>เปิดดู</Link>
        </Button>
      ) : null}
    </div>
  );
}
