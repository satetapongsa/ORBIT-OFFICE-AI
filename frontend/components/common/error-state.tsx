import { AlertTriangle, RotateCw } from "lucide-react";

import { Button } from "@/components/ui/button";

interface ErrorStateProps {
  title?: string;
  message: string;
  requestId?: string | null;
  onRetry?: () => void;
  retrying?: boolean;
}

export function ErrorState({
  title = "ไม่สามารถโหลดข้อมูลได้",
  message,
  requestId,
  onRetry,
  retrying = false,
}: ErrorStateProps) {
  return (
    <div
      role="alert"
      className="border-destructive/30 bg-destructive/5 flex flex-col items-center gap-3 rounded-xl border px-6 py-10 text-center"
    >
      <AlertTriangle className="text-destructive size-8" aria-hidden />
      <div className="space-y-1">
        <p className="font-medium">{title}</p>
        <p className="text-muted-foreground text-sm">{message}</p>
        {requestId ? (
          <p className="text-muted-foreground font-mono text-xs">รหัสอ้างอิง: {requestId}</p>
        ) : null}
      </div>
      {onRetry ? (
        <Button variant="outline" size="sm" onClick={onRetry} disabled={retrying}>
          <RotateCw className={retrying ? "animate-spin" : undefined} aria-hidden />
          ลองใหม่
        </Button>
      ) : null}
    </div>
  );
}
