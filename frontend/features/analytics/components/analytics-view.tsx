"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  FileSpreadsheet,
  FileText,
  Files,
  Headset,
  ListChecks,
  Loader2,
  Sparkles,
  type LucideIcon,
} from "lucide-react";
import { useId, useState, type ReactNode } from "react";
import { toast } from "sonner";

import { ColumnChart, type ColumnDatum } from "@/components/charts/column-chart";
import { ErrorState } from "@/components/common/error-state";
import { NativeSelect } from "@/components/common/native-select";
import { PageHeader } from "@/components/common/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { useAiStatus } from "@/features/assistant/hooks/use-assistant";
import { useSession } from "@/features/auth/hooks/use-session";
import { CATEGORY_LABELS as DOCUMENT_CATEGORY_LABELS } from "@/features/documents/labels";
import { TICKET_CATEGORY_LABELS, TICKET_STATUS_LABELS } from "@/features/helpdesk/labels";
import { TASK_PRIORITY_LABELS, TASK_STATUS_LABELS } from "@/features/tasks/labels";
import { formatDateTime, formatDay, numberFormat } from "@/lib/format";
import {
  analyticsQueryKeys,
  downloadReport,
  getAnalyticsOverview,
  summarizeAnalytics,
  type AnalyticsOverview,
  type AnalyticsParams,
  type AnalyticsScope,
} from "@/services/analytics";
import { ApiError } from "@/services/api-client";

export const SCOPE_LABELS: Record<AnalyticsScope, string> = {
  own: "งานของฉัน",
  department: "แผนกของฉัน",
  all: "ทั้งองค์กร",
};

const PRESETS = [
  { value: "7", label: "7 วันล่าสุด" },
  { value: "30", label: "30 วันล่าสุด" },
  { value: "90", label: "90 วันล่าสุด" },
  { value: "365", label: "1 ปีล่าสุด" },
  { value: "custom", label: "กำหนดเอง" },
] as const;
type Preset = (typeof PRESETS)[number]["value"];

/** `YYYY-MM-DD` in Bangkok time, `days` days before today (0 = today). */
export function bangkokDay(daysAgo = 0, now: Date = new Date()): string {
  const shifted = new Date(now.getTime() - daysAgo * 86_400_000);
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Bangkok" }).format(shifted);
}

/** Lookup with a readable fallback for keys the UI has no label for. */
function label(map: Record<string, string>, key: string): string {
  return map[key] ?? key;
}

function hours(value: number | null): string {
  if (value === null) return "—";
  if (value < 48) return `${numberFormat.format(value)} ชม.`;
  return `${numberFormat.format(Math.round((value / 24) * 10) / 10)} วัน`;
}

function Metric({
  label: name,
  value,
  icon: Icon,
  hint,
  tone,
}: {
  label: string;
  value: string;
  icon: LucideIcon;
  hint?: ReactNode;
  tone?: "warn";
}) {
  return (
    <Card className="gap-0 py-4" data-testid="metric">
      <CardContent className="space-y-2 px-3 sm:px-4">
        <div className="flex items-center justify-between gap-2">
          <p className="text-muted-foreground text-xs sm:text-sm">{name}</p>
          <span
            className={
              tone === "warn"
                ? "hidden size-8 shrink-0 items-center justify-center rounded-lg bg-red-50 text-red-700 sm:flex"
                : "bg-primary/10 text-primary hidden size-8 shrink-0 items-center justify-center rounded-lg sm:flex"
            }
          >
            <Icon className="size-4" aria-hidden />
          </span>
        </div>
        <p className="text-2xl font-semibold tracking-tight tabular-nums sm:text-3xl">{value}</p>
        {hint ? <p className="text-muted-foreground text-xs">{hint}</p> : null}
      </CardContent>
    </Card>
  );
}

function Bars({ title, rows }: { title: string; rows: { label: string; count: number }[] }) {
  if (rows.length === 0)
    return <p className="text-muted-foreground text-sm">ไม่มีข้อมูลในช่วงนี้</p>;
  const max = Math.max(1, ...rows.map((r) => r.count));
  return (
    <ul className="space-y-3" aria-label={title}>
      {rows.map((row) => (
        <li
          key={row.label}
          className="grid grid-cols-[minmax(0,10rem)_1fr_auto] items-center gap-3 text-sm"
        >
          <span className="truncate" title={row.label}>
            {row.label}
          </span>
          <span className="bg-muted/60 h-2.5 overflow-hidden rounded-r-[4px]" aria-hidden>
            <span
              className="block h-full rounded-r-[4px]"
              style={{ width: `${(row.count / max) * 100}%`, backgroundColor: "var(--chart-1)" }}
            />
          </span>
          <span className="text-right tabular-nums">{numberFormat.format(row.count)}</span>
        </li>
      ))}
    </ul>
  );
}

function daily(rows: AnalyticsOverview["tasks"]["daily"], key: "opened" | "closed"): ColumnDatum[] {
  return rows.map((d) => ({
    key: d.date,
    label: formatDay(d.date, { month: undefined }),
    fullLabel: formatDay(d.date, { year: "numeric" }),
    values: { value: d[key] },
  }));
}

function ChartCard({
  title,
  description,
  data,
  seriesLabel,
  unit,
}: {
  title: string;
  description: string;
  data: ColumnDatum[];
  seriesLabel: string;
  unit: string;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent>
        <ColumnChart
          title={title}
          data={data}
          series={[{ key: "value", label: seriesLabel, color: "var(--chart-1)" }]}
          unit={unit}
        />
      </CardContent>
    </Card>
  );
}

function SummaryCard({ params }: { params: AnalyticsParams }) {
  const status = useAiStatus();
  const summary = useMutation({ mutationFn: () => summarizeAnalytics(params) });
  const key = JSON.stringify(params);
  const [forKey, setForKey] = useState<string | null>(null);
  const current = forKey === key ? summary.data : undefined;

  return (
    <Card data-testid="ai-summary">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Sparkles className="text-primary size-4" aria-hidden />
          สรุปด้วยผู้ช่วย AI
        </CardTitle>
        <CardDescription>
          ผู้ช่วยอ่านเฉพาะตัวเลขในรายงานนี้ (ไม่อ่านรายละเอียดงานหรือเอกสาร) โปรดตรวจสอบก่อนนำไปใช้
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {status.isPending ? (
          <Skeleton className="h-9 w-40" />
        ) : !status.data?.enabled ? (
          <p className="text-muted-foreground text-sm">
            ผู้ช่วย AI ยังไม่ได้เปิดใช้งาน ผู้ดูแลระบบตั้งค่าได้ตามคู่มือการติดตั้ง
          </p>
        ) : (
          <>
            <Button
              variant="outline"
              disabled={summary.isPending}
              onClick={() =>
                summary.mutate(undefined, {
                  onSuccess: () => setForKey(key),
                  onError: (e) =>
                    toast.error(e instanceof ApiError ? e.message : "สรุปรายงานไม่สำเร็จ"),
                })
              }
            >
              {summary.isPending ? (
                <Loader2 className="animate-spin" aria-hidden />
              ) : (
                <Sparkles aria-hidden />
              )}
              {current ? "สรุปใหม่" : "สรุปรายงานนี้"}
            </Button>
            {current ? (
              <div className="bg-muted/40 rounded-lg p-4">
                {/* Model output is untrusted: plain text only. */}
                <p className="text-sm leading-relaxed whitespace-pre-wrap">{current.summary}</p>
                <p className="text-muted-foreground mt-2 text-xs">
                  {current.model} · {formatDateTime(current.generated_at)}
                </p>
              </div>
            ) : null}
          </>
        )}
      </CardContent>
    </Card>
  );
}

function ExportButtons({ params }: { params: AnalyticsParams }) {
  const [busy, setBusy] = useState<"xlsx" | "pdf" | null>(null);
  const run = async (format: "xlsx" | "pdf") => {
    setBusy(format);
    try {
      const name = await downloadReport(params, format);
      toast.success(`ดาวน์โหลด ${name} แล้ว`);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "ส่งออกรายงานไม่สำเร็จ");
    } finally {
      setBusy(null);
    }
  };
  return (
    <div className="flex flex-wrap gap-2">
      <Button variant="outline" disabled={busy !== null} onClick={() => void run("xlsx")}>
        {busy === "xlsx" ? (
          <Loader2 className="animate-spin" aria-hidden />
        ) : (
          <FileSpreadsheet aria-hidden />
        )}
        Excel
      </Button>
      <Button variant="outline" disabled={busy !== null} onClick={() => void run("pdf")}>
        {busy === "pdf" ? (
          <Loader2 className="animate-spin" aria-hidden />
        ) : (
          <FileText aria-hidden />
        )}
        PDF
      </Button>
    </div>
  );
}

function Report({ data, params }: { data: AnalyticsOverview; params: AnalyticsParams }) {
  const { has } = useSession();
  const t = data.tasks;
  const k = data.tickets;
  const rate = t.completion_rate === null ? "—" : `${Math.round(t.completion_rate * 100)}%`;
  const days = t.daily.length;
  return (
    <div className="space-y-6">
      <section aria-label="สรุปตัวเลข" className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
        <Metric
          label="งานที่ยังไม่เสร็จ"
          value={numberFormat.format(t.open)}
          icon={ListChecks}
          hint={`สร้างใหม่ ${numberFormat.format(t.created)} งานในช่วงนี้`}
        />
        <Metric
          label="งานเลยกำหนด"
          value={numberFormat.format(t.overdue)}
          icon={AlertTriangle}
          tone={t.overdue > 0 ? "warn" : undefined}
          hint="ยังไม่เสร็จและเลยกำหนดส่งแล้ว"
        />
        <Metric
          label="งานที่เสร็จในช่วงนี้"
          value={numberFormat.format(t.completed)}
          icon={CheckCircle2}
          hint={`เทียบกับงานที่สร้าง ${rate}`}
        />
        <Metric
          label="เวลาเฉลี่ยจนงานเสร็จ"
          value={hours(t.avg_completion_hours)}
          icon={Clock}
          hint="นับจากวันที่สร้างงาน"
        />
        <Metric
          label="แจ้งปัญหาไอทีที่ยังเปิดอยู่"
          value={numberFormat.format(k.open)}
          icon={Headset}
          hint={`แจ้งใหม่ ${numberFormat.format(k.opened)} · แก้ไขแล้ว ${numberFormat.format(k.resolved)}`}
        />
        <Metric
          label="เวลาเฉลี่ยในการแก้ไขปัญหา"
          value={hours(k.avg_resolution_hours)}
          icon={Clock}
          hint="เฉพาะเรื่องที่แก้ไขในช่วงนี้"
        />
        <Metric
          label="เอกสาร"
          value={numberFormat.format(data.documents.total)}
          icon={Files}
          hint={`อัปโหลดใหม่ ${numberFormat.format(data.documents.uploaded)} ไฟล์ในช่วงนี้`}
        />
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        <ChartCard
          title="งานที่เสร็จต่อวัน"
          description={`${days} วัน ตามเวลา ${data.timezone}`}
          data={daily(t.daily, "closed")}
          seriesLabel="งานที่เสร็จ"
          unit="งาน"
        />
        <ChartCard
          title="แจ้งปัญหาไอทีใหม่ต่อวัน"
          description={`${days} วัน ตามเวลา ${data.timezone}`}
          data={daily(k.daily, "opened")}
          seriesLabel="แจ้งปัญหาใหม่"
          unit="เรื่อง"
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>งานตามสถานะ</CardTitle>
            <CardDescription>งานทั้งหมดในขอบเขตนี้</CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            <Bars
              title="งานตามสถานะ"
              rows={t.by_status.map((r) => ({
                label: label(TASK_STATUS_LABELS, r.key),
                count: r.count,
              }))}
            />
            {t.open_by_priority.length > 0 ? (
              <div className="space-y-2">
                <p className="text-muted-foreground text-xs font-medium">งานค้างตามความสำคัญ</p>
                <Bars
                  title="งานค้างตามความสำคัญ"
                  rows={t.open_by_priority.map((r) => ({
                    label: label(TASK_PRIORITY_LABELS, r.key),
                    count: r.count,
                  }))}
                />
              </div>
            ) : null}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>แจ้งปัญหาไอทีตามหมวด</CardTitle>
            <CardDescription>เรื่องที่แจ้งในช่วงนี้</CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            <Bars
              title="แจ้งปัญหาตามหมวด"
              rows={k.by_category.map((r) => ({
                label: label(TICKET_CATEGORY_LABELS, r.key),
                count: r.count,
              }))}
            />
            {k.by_status.length > 0 ? (
              <div className="space-y-2">
                <p className="text-muted-foreground text-xs font-medium">ทุกเรื่องตามสถานะ</p>
                <Bars
                  title="แจ้งปัญหาตามสถานะ"
                  rows={k.by_status.map((r) => ({
                    label: label(TICKET_STATUS_LABELS, r.key),
                    count: r.count,
                  }))}
                />
              </div>
            ) : null}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>เอกสารตามประเภท</CardTitle>
            <CardDescription>
              {data.scope === "own" ? "เอกสารที่คุณเป็นเจ้าของ" : "เอกสารของขอบเขตนี้"}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Bars
              title="เอกสารตามประเภท"
              rows={data.documents.by_category.map((r) => ({
                label: label(DOCUMENT_CATEGORY_LABELS, r.key),
                count: r.count,
              }))}
            />
          </CardContent>
        </Card>
      </div>

      {t.workload.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>ภาระงานรายบุคคล</CardTitle>
            <CardDescription>งานค้างและงานที่เสร็จของผู้รับผิดชอบแต่ละคน</CardDescription>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="workload">
              <thead>
                <tr className="text-muted-foreground border-b text-left text-xs">
                  <th scope="col" className="py-2 pr-4 font-medium">
                    พนักงาน
                  </th>
                  <th scope="col" className="py-2 pr-4 text-right font-medium">
                    งานค้าง
                  </th>
                  <th scope="col" className="py-2 pr-4 text-right font-medium">
                    เลยกำหนด
                  </th>
                  <th scope="col" className="py-2 text-right font-medium">
                    เสร็จในช่วงนี้
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {t.workload.map((w) => (
                  <tr key={w.user.id}>
                    <th scope="row" className="py-2 pr-4 text-left font-normal">
                      {w.user.display_name}
                    </th>
                    <td className="py-2 pr-4 text-right tabular-nums">{w.open}</td>
                    <td
                      className={
                        w.overdue > 0
                          ? "py-2 pr-4 text-right font-medium text-red-700 tabular-nums"
                          : "py-2 pr-4 text-right tabular-nums"
                      }
                    >
                      {w.overdue}
                    </td>
                    <td className="py-2 text-right tabular-nums">{w.completed}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      ) : null}

      {has("ai:chat") ? <SummaryCard params={params} /> : null}
    </div>
  );
}

/** The widest scope the session allows (the backend re-checks every request). */
function defaultScope(has: (p: string) => boolean, hasDepartment: boolean): AnalyticsScope {
  if (has("analytics:read_all")) return "all";
  if (has("analytics:read_department") && hasDepartment) return "department";
  return "own";
}

export function AnalyticsView() {
  const { has, me } = useSession();
  const ids = { preset: useId(), from: useId(), to: useId() };
  const [scope, setScope] = useState<AnalyticsScope>(() =>
    defaultScope(has, Boolean(me?.user.department)),
  );
  const [preset, setPreset] = useState<Preset>("30");
  const [custom, setCustom] = useState({ from: bangkokDay(29), to: bangkokDay(0) });

  const params: AnalyticsParams =
    preset === "custom"
      ? { scope, dateFrom: custom.from, dateTo: custom.to }
      : { scope, dateFrom: bangkokDay(Number(preset) - 1), dateTo: bangkokDay(0) };
  const overview = useQuery({
    queryKey: analyticsQueryKeys.overview(params),
    queryFn: ({ signal }) => getAnalyticsOverview(params, signal),
    placeholderData: (previous) => previous,
    staleTime: 30_000,
  });
  const data = overview.data;
  const scopes = data?.available_scopes ?? [scope];

  return (
    <>
      <PageHeader
        title="รายงานและการวิเคราะห์"
        description="สถิติงาน การแจ้งปัญหาไอที และเอกสาร ตามขอบเขตที่คุณมีสิทธิ์ดู"
        actions={data?.can_export ? <ExportButtons params={params} /> : null}
      />

      <div className="mb-6 flex flex-wrap items-end gap-4">
        {scopes.length > 1 ? (
          <div role="tablist" aria-label="ขอบเขตรายงาน" className="flex flex-wrap gap-1.5">
            {scopes.map((s) => (
              <Button
                key={s}
                role="tab"
                aria-selected={scope === s}
                size="sm"
                variant={scope === s ? "default" : "outline"}
                onClick={() => setScope(s)}
              >
                {SCOPE_LABELS[s]}
                {s === "department" && data?.department && scope === s
                  ? ` · ${data.department.name}`
                  : ""}
              </Button>
            ))}
          </div>
        ) : null}
        <div className="space-y-1.5">
          <Label htmlFor={ids.preset}>ช่วงเวลา</Label>
          <NativeSelect
            id={ids.preset}
            value={preset}
            onChange={(e) => setPreset(e.target.value as Preset)}
          >
            {PRESETS.map((p) => (
              <option key={p.value} value={p.value}>
                {p.label}
              </option>
            ))}
          </NativeSelect>
        </div>
        {preset === "custom" ? (
          <>
            <div className="space-y-1.5">
              <Label htmlFor={ids.from}>ตั้งแต่</Label>
              <Input
                id={ids.from}
                type="date"
                value={custom.from}
                max={custom.to}
                onChange={(e) =>
                  e.target.value && setCustom((c) => ({ ...c, from: e.target.value }))
                }
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor={ids.to}>ถึง</Label>
              <Input
                id={ids.to}
                type="date"
                value={custom.to}
                min={custom.from}
                max={bangkokDay(0)}
                onChange={(e) => e.target.value && setCustom((c) => ({ ...c, to: e.target.value }))}
              />
            </div>
          </>
        ) : null}
        {overview.isFetching && data ? (
          <Loader2
            className="text-muted-foreground mb-2 size-4 animate-spin"
            aria-label="กำลังโหลด"
          />
        ) : null}
      </div>

      {overview.isPending ? (
        <div className="space-y-4" aria-busy="true" aria-label="กำลังโหลดรายงาน">
          <div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
            {Array.from({ length: 4 }, (_, i) => (
              <Skeleton key={i} className="h-32 rounded-xl" />
            ))}
          </div>
          <Skeleton className="h-64 rounded-xl" />
        </div>
      ) : overview.isError && !data ? (
        <ErrorState
          message={overview.error.message}
          requestId={overview.error instanceof ApiError ? overview.error.requestId : null}
          onRetry={() => void overview.refetch()}
          retrying={overview.isFetching}
        />
      ) : data ? (
        <>
          {overview.isError ? (
            <p role="alert" className="text-destructive mb-4 text-sm">
              {overview.error.message}
            </p>
          ) : null}
          <Report data={data} params={params} />
        </>
      ) : null}
    </>
  );
}
