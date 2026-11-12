"use client";

import { RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { ErrorState } from "@/components/common/error-state";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/features/system-status/components/status-badge";
import { useReadiness } from "@/features/system-status/hooks/use-readiness";
import { componentLabel, detailLabel } from "@/features/system-status/labels";
import { ApiError } from "@/services/api-client";
import type { ComponentHealth, Readiness } from "@/services/health";

const dateFormatter = new Intl.DateTimeFormat("th-TH", {
  dateStyle: "medium",
  timeStyle: "medium",
  timeZone: "Asia/Bangkok",
});

function ComponentDetail({ detail }: { detail: string }) {
  const { text, technical } = detailLabel(detail);
  return <p className={technical ? "font-mono break-all" : undefined}>{text}</p>;
}

function ComponentCard({ component }: { component: ComponentHealth }) {
  const { title, description } = componentLabel(component.name);
  return (
    <Card data-testid={`component-${component.name}`} size="sm">
      <CardHeader className="flex flex-row items-start justify-between gap-3">
        <div className="space-y-1">
          <CardTitle className="text-base">{title}</CardTitle>
          <CardDescription>{description}</CardDescription>
        </div>
        <StatusBadge status={component.status} />
      </CardHeader>
      <CardContent className="text-muted-foreground space-y-1 text-xs">
        <p>{component.required ? "จำเป็นต่อการทำงานของระบบ" : "ทางเลือก (ไม่บังคับ)"}</p>
        {component.latency_ms != null ? (
          <p>เวลาตอบสนอง {component.latency_ms.toFixed(1)} ms</p>
        ) : null}
        {component.detail ? <ComponentDetail detail={component.detail} /> : null}
      </CardContent>
    </Card>
  );
}

function Summary({ data }: { data: Readiness }) {
  const ok = data.status === "ok";
  return (
    <Card className={ok ? "ring-emerald-300" : "ring-amber-300"}>
      <CardHeader className="flex flex-row items-center justify-between gap-3">
        <div className="space-y-1">
          <CardTitle>{ok ? "ระบบพร้อมใช้งาน" : "ระบบขัดข้องบางส่วน"}</CardTitle>
          <CardDescription>
            ตรวจสอบล่าสุด {dateFormatter.format(new Date(data.checked_at))}
            {data.environment ? (
              <>
                {" "}
                · สภาพแวดล้อม <span className="font-mono">{data.environment}</span>
              </>
            ) : null}{" "}
            · เวอร์ชัน <span className="font-mono">{data.version}</span>
          </CardDescription>
        </div>
        <StatusBadge status={data.status} />
      </CardHeader>
    </Card>
  );
}

function LoadingSkeleton() {
  return (
    <div className="space-y-4" aria-busy="true" aria-label="กำลังโหลดสถานะระบบ">
      <Skeleton className="h-24 w-full rounded-xl" />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {Array.from({ length: 5 }, (_, i) => (
          <Skeleton key={i} className="h-32 rounded-xl" />
        ))}
      </div>
    </div>
  );
}

export function SystemStatusPanel() {
  const { data, error, isPending, isFetching, refetch } = useReadiness();

  async function handleRefresh() {
    const result = await refetch();
    if (result.isError) toast.error("ตรวจสอบสถานะระบบไม่สำเร็จ");
    else if (result.data?.status === "ok") toast.success("ทุกส่วนของระบบทำงานปกติ");
    else toast.warning("พบส่วนประกอบของระบบที่ขัดข้อง");
  }

  const refreshButton = (
    <Button variant="outline" size="sm" onClick={handleRefresh} disabled={isFetching}>
      <RefreshCw className={isFetching ? "animate-spin" : undefined} aria-hidden />
      ตรวจสอบอีกครั้ง
    </Button>
  );

  if (isPending) return <LoadingSkeleton />;

  if (error) {
    const apiError = error instanceof ApiError ? error : null;
    return (
      <ErrorState
        title="ไม่สามารถเชื่อมต่อกับเซิร์ฟเวอร์ API ได้"
        message={apiError?.message ?? "เกิดข้อผิดพลาดที่ไม่ทราบสาเหตุ"}
        requestId={apiError?.requestId}
        onRetry={handleRefresh}
        retrying={isFetching}
      />
    );
  }

  if (data.details_hidden) {
    return (
      <div className="space-y-6">
        <div className="flex justify-end">{refreshButton}</div>
        <Summary data={data} />
        <p className="text-muted-foreground text-sm" data-testid="details-hidden">
          รายละเอียดของแต่ละบริการแสดงเฉพาะผู้ดูแลระบบ
        </p>
      </div>
    );
  }

  const required = data.components.filter((c) => c.required);
  const optional = data.components.filter((c) => !c.required);

  return (
    <div className="space-y-6">
      <div className="flex justify-end">{refreshButton}</div>
      <Summary data={data} />
      <section aria-labelledby="core-services" className="space-y-3">
        <h2 id="core-services" className="text-muted-foreground text-sm font-medium">
          บริการหลัก
        </h2>
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {required.map((c) => (
            <ComponentCard key={c.name} component={c} />
          ))}
        </div>
      </section>
      <section aria-labelledby="ai-services" className="space-y-3">
        <h2 id="ai-services" className="text-muted-foreground text-sm font-medium">
          บริการ AI
        </h2>
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {optional.map((c) => (
            <ComponentCard key={c.name} component={c} />
          ))}
        </div>
      </section>
    </div>
  );
}
