"use client";

import {
  Bell,
  Building2,
  FileText,
  KeyRound,
  LogIn,
  MonitorSmartphone,
  ShieldAlert,
  ShieldCheck,
  Users,
} from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import { ColumnChart, type ColumnDatum } from "@/components/charts/column-chart";
import { ErrorState } from "@/components/common/error-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { roleLabel } from "@/features/auth/labels";
import { useSession } from "@/features/auth/hooks/use-session";
import { ActivityList } from "@/features/dashboard/components/activity-list";
import { DepartmentBars } from "@/features/dashboard/components/department-bars";
import { StatCard } from "@/features/dashboard/components/stat-card";
import { useDashboardSummary } from "@/features/dashboard/hooks/use-dashboard-summary";
import { NotificationItem } from "@/features/notifications/components/notification-item";
import { ProcessingBadge } from "@/features/documents/components/processing-badge";
import { DueLabel, TaskStatusBadge } from "@/features/tasks/components/task-badges";
import {
  formatDateTime,
  formatDay,
  formatLongDate,
  formatRelative,
  numberFormat,
} from "@/lib/format";
import { ApiError } from "@/services/api-client";
import type { DashboardSummary } from "@/services/dashboard";
import { processingStatusSchema, type ProcessingStatus } from "@/services/documents";

const SERIES_SIGN_INS = { key: "sign_ins", label: "เข้าสู่ระบบสำเร็จ", color: "var(--chart-1)" };
const SERIES_FAILED = { key: "failed", label: "เข้าสู่ระบบไม่สำเร็จ", color: "var(--chart-2)" };

function dayDatum(date: string, values: Record<string, number>): ColumnDatum {
  return {
    key: date,
    label: formatDay(date, { month: undefined }),
    fullLabel: formatDay(date, { year: "numeric" }),
    values,
  };
}

function Section({
  title,
  description,
  children,
  testId,
}: {
  title: string;
  description: string;
  children: ReactNode;
  testId: string;
}) {
  return (
    <section aria-labelledby={`${testId}-title`} className="space-y-4" data-testid={testId}>
      <div className="space-y-0.5">
        <h2 id={`${testId}-title`} className="text-lg font-semibold tracking-tight">
          {title}
        </h2>
        <p className="text-muted-foreground text-sm">{description}</p>
      </div>
      {children}
    </section>
  );
}

function DashboardSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true" aria-label="กำลังโหลดแดชบอร์ด">
      <div className="space-y-2">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-4 w-80" />
      </div>
      <div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
        {Array.from({ length: 4 }, (_, i) => (
          <Skeleton key={i} className="h-32 rounded-xl" />
        ))}
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <Skeleton className="h-72 rounded-xl lg:col-span-2" />
        <Skeleton className="h-72 rounded-xl" />
      </div>
    </div>
  );
}

function PersonalSection({ data, selfId }: { data: DashboardSummary; selfId?: string }) {
  const { account, notifications, my_activity: activity } = data;
  const signIns = activity.daily_sign_ins.reduce((sum, d) => sum + d.count, 0);
  const chart = activity.daily_sign_ins.map((d) => dayDatum(d.date, { sign_ins: d.count }));

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
        <StatCard
          testId="stat-unread"
          label="การแจ้งเตือนที่ยังไม่อ่าน"
          value={notifications.unread_count}
          icon={Bell}
          hint={
            <Link
              href="/notifications"
              className="hover:text-foreground underline-offset-2 hover:underline"
            >
              ดูการแจ้งเตือนทั้งหมด
            </Link>
          }
        />
        <StatCard
          testId="stat-sessions"
          label="อุปกรณ์ที่เข้าสู่ระบบอยู่"
          value={account.active_sessions}
          icon={MonitorSmartphone}
          hint="เซสชันที่ยังใช้งานได้ของบัญชีนี้"
        />
        <StatCard
          testId="stat-sign-ins"
          label={`การเข้าสู่ระบบ ${data.period_days} วันล่าสุด`}
          value={signIns}
          icon={LogIn}
          hint="เฉพาะบัญชีของคุณ"
        />
        {data.documents ? (
          <StatCard
            testId="stat-documents"
            label="เอกสารที่คุณเข้าถึงได้"
            value={data.documents.accessible_count}
            icon={FileText}
            hint={
              <Link
                href="/documents"
                className="hover:text-foreground underline-offset-2 hover:underline"
              >
                เปิดศูนย์เอกสาร
              </Link>
            }
          />
        ) : null}
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>การเข้าสู่ระบบของฉัน</CardTitle>
            <CardDescription>
              จำนวนครั้งต่อวันในช่วง {data.period_days} วันที่ผ่านมา
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ColumnChart
              title="จำนวนการเข้าสู่ระบบของฉันต่อวัน"
              data={chart}
              series={[SERIES_SIGN_INS]}
              unit="ครั้ง"
            />
          </CardContent>
        </Card>

        <Card data-testid="account-security">
          <CardHeader>
            <CardTitle>บัญชีและความปลอดภัย</CardTitle>
            <CardDescription>ตรวจสอบว่าการเข้าใช้งานล่าสุดเป็นของคุณ</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4 text-sm">
            <dl className="space-y-3">
              <div>
                <dt className="text-muted-foreground text-xs">เข้าสู่ระบบครั้งก่อน</dt>
                <dd>
                  {account.previous_login_at
                    ? formatDateTime(account.previous_login_at, data.timezone)
                    : "นี่เป็นการเข้าสู่ระบบครั้งแรก"}
                </dd>
              </div>
              <div>
                <dt className="text-muted-foreground text-xs">เปลี่ยนรหัสผ่านล่าสุด</dt>
                <dd>
                  {account.password_changed_at
                    ? formatDateTime(account.password_changed_at, data.timezone)
                    : "—"}
                </dd>
              </div>
              <div>
                <dt className="text-muted-foreground text-xs">แผนก</dt>
                <dd>{account.department?.name ?? "ไม่ระบุแผนก"}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground mb-1 text-xs">บทบาท</dt>
                <dd className="flex flex-wrap gap-1.5">
                  {account.roles.length > 0 ? (
                    account.roles.map((r) => (
                      <Badge key={r.id} variant="secondary">
                        {roleLabel(r.code, r.name)}
                      </Badge>
                    ))
                  ) : (
                    <span className="text-muted-foreground">ยังไม่มีบทบาท</span>
                  )}
                </dd>
              </div>
            </dl>
            <Button asChild variant="outline" size="sm" className="w-full">
              <Link href="/account">
                <KeyRound aria-hidden />
                จัดการบัญชีและรหัสผ่าน
              </Link>
            </Button>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card data-testid="notification-preview">
          <CardHeader>
            <CardTitle>การแจ้งเตือนล่าสุด</CardTitle>
            <CardDescription>
              {notifications.unread_count > 0
                ? `ยังไม่อ่าน ${numberFormat.format(notifications.unread_count)} รายการ`
                : "อ่านครบทุกรายการแล้ว"}
            </CardDescription>
            <CardAction>
              <Button asChild variant="ghost" size="sm">
                <Link href="/notifications">ดูทั้งหมด</Link>
              </Button>
            </CardAction>
          </CardHeader>
          <CardContent className="space-y-1">
            {notifications.latest.length === 0 ? (
              <p className="text-muted-foreground py-6 text-center text-sm">ยังไม่มีการแจ้งเตือน</p>
            ) : (
              notifications.latest.map((n) => (
                <NotificationItem key={n.id} notification={n} compact />
              ))
            )}
          </CardContent>
        </Card>

        <Card data-testid="my-activity">
          <CardHeader>
            <CardTitle>กิจกรรมล่าสุดของบัญชี</CardTitle>
            <CardDescription>
              สิ่งที่คุณทำ และการเปลี่ยนแปลงที่ผู้อื่นทำกับบัญชีของคุณ
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ActivityList
              items={activity.recent}
              selfId={selfId}
              timeZone={data.timezone}
              emptyText="ยังไม่มีกิจกรรม"
            />
          </CardContent>
        </Card>
      </div>

      {data.tasks || data.documents ? (
        <div className="grid gap-4 lg:grid-cols-2">
          {data.tasks ? <TasksCard tasks={data.tasks} /> : null}
          {data.documents ? <DocumentsCard documents={data.documents} /> : null}
        </div>
      ) : null}
    </div>
  );
}

function TasksCard({ tasks }: { tasks: NonNullable<DashboardSummary["tasks"]> }) {
  return (
    <Card data-testid="tasks-card">
      <CardHeader>
        <CardTitle>งานของฉัน</CardTitle>
        <CardDescription>
          งานที่ยังไม่เสร็จ {numberFormat.format(tasks.open_assigned)} งาน
          {tasks.overdue > 0 ? ` · เลยกำหนด ${numberFormat.format(tasks.overdue)}` : ""}
          {tasks.due_soon > 0 ? ` · ครบกำหนดใน 7 วัน ${numberFormat.format(tasks.due_soon)}` : ""}
        </CardDescription>
        <CardAction>
          <Button asChild variant="ghost" size="sm">
            <Link href="/tasks">ดูทั้งหมด</Link>
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent>
        {tasks.upcoming.length === 0 ? (
          <p className="text-muted-foreground py-6 text-center text-sm">ไม่มีงานค้าง</p>
        ) : (
          <ul className="divide-y">
            {tasks.upcoming.map((task) => (
              <li key={task.id}>
                <Link
                  href={`/tasks/${task.id}`}
                  className="hover:bg-muted/50 flex items-center gap-3 rounded-md px-2 py-2.5 text-sm"
                >
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium">{task.title}</span>
                    <DueLabel dueAt={task.due_at} overdue={task.is_overdue} />
                  </span>
                  <TaskStatusBadge status={task.status} />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function DocumentsCard({ documents }: { documents: NonNullable<DashboardSummary["documents"]> }) {
  return (
    <Card data-testid="documents-card">
      <CardHeader>
        <CardTitle>เอกสารล่าสุด</CardTitle>
        <CardDescription>
          เอกสารของคุณ {numberFormat.format(documents.my_documents)} รายการ
          {documents.my_processing > 0
            ? ` · กำลังประมวลผล ${numberFormat.format(documents.my_processing)}`
            : ""}
          {documents.my_failed > 0
            ? ` · ประมวลผลไม่สำเร็จ ${numberFormat.format(documents.my_failed)}`
            : ""}
        </CardDescription>
        <CardAction>
          <Button asChild variant="ghost" size="sm">
            <Link href="/documents">ดูทั้งหมด</Link>
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent>
        {documents.recent.length === 0 ? (
          <p className="text-muted-foreground py-6 text-center text-sm">
            ยังไม่มีเอกสารที่คุณเข้าถึงได้
          </p>
        ) : (
          <ul className="divide-y">
            {documents.recent.map((doc) => (
              <li key={doc.id}>
                <Link
                  href={`/documents/${doc.id}`}
                  className="hover:bg-muted/50 flex items-center gap-3 rounded-md px-2 py-2.5 text-sm"
                >
                  <span className="bg-primary/10 text-primary flex size-8 shrink-0 items-center justify-center rounded-md text-[10px] font-semibold">
                    {doc.file_type ?? "—"}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium">{doc.title}</span>
                    <span className="text-muted-foreground block text-xs">
                      {formatRelative(doc.updated_at)}
                    </span>
                  </span>
                  {doc.processing_status && isProcessingStatus(doc.processing_status) ? (
                    <ProcessingBadge status={doc.processing_status} />
                  ) : null}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function isProcessingStatus(value: string): value is ProcessingStatus {
  return (processingStatusSchema.options as readonly string[]).includes(value);
}

function OrganizationSection({ org }: { org: NonNullable<DashboardSummary["organization"]> }) {
  return (
    <Section
      testId="organization-section"
      title="ภาพรวมองค์กร"
      description="แสดงเฉพาะผู้ที่มีสิทธิ์ดูข้อมูลผู้ใช้"
    >
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-1">
          <StatCard
            testId="stat-active-users"
            label="พนักงานที่ใช้งานอยู่"
            value={org.active_users}
            icon={Users}
            hint={`บัญชีที่ถูกระงับ ${numberFormat.format(org.inactive_users)} บัญชี`}
          />
          <StatCard
            testId="stat-departments"
            label="แผนก"
            value={org.departments}
            icon={Building2}
            hint="แผนกที่เปิดใช้งาน"
          />
        </div>
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>พนักงานแยกตามแผนก</CardTitle>
            <CardDescription>นับเฉพาะบัญชีที่ใช้งานอยู่</CardDescription>
          </CardHeader>
          <CardContent>
            {org.users_by_department.length === 0 ? (
              <p className="text-muted-foreground py-6 text-center text-sm">ยังไม่มีพนักงาน</p>
            ) : (
              <DepartmentBars rows={org.users_by_department} />
            )}
          </CardContent>
        </Card>
      </div>
    </Section>
  );
}

function SecuritySection({
  security,
  data,
  selfId,
}: {
  security: NonNullable<DashboardSummary["security"]>;
  data: DashboardSummary;
  selfId?: string;
}) {
  const chart = security.daily.map((d) =>
    dayDatum(d.date, { sign_ins: d.sign_ins, failed: d.failed_sign_ins }),
  );
  return (
    <Section
      testId="security-section"
      title="ความปลอดภัยของระบบ"
      description={`การเข้าสู่ระบบทั้งองค์กรในช่วง ${data.period_days} วัน (จากบันทึกการใช้งานระบบ)`}
    >
      <div className="grid grid-cols-2 gap-3 sm:gap-4">
        <StatCard
          testId="stat-org-sign-ins"
          label="เข้าสู่ระบบสำเร็จ"
          value={security.sign_ins}
          icon={ShieldCheck}
          hint={`ทั้งองค์กร ${data.period_days} วันล่าสุด`}
        />
        <StatCard
          testId="stat-failed-sign-ins"
          label="เข้าสู่ระบบไม่สำเร็จ"
          value={security.failed_sign_ins}
          icon={ShieldAlert}
          hint={`ถูกจำกัดการเข้าสู่ระบบชั่วคราว ${numberFormat.format(security.rate_limited)} ครั้ง`}
        />
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>การเข้าสู่ระบบรายวัน</CardTitle>
            <CardDescription>สำเร็จและไม่สำเร็จ ซ้อนกันในแต่ละวัน</CardDescription>
          </CardHeader>
          <CardContent>
            <ColumnChart
              title="จำนวนการเข้าสู่ระบบทั้งองค์กรต่อวัน"
              data={chart}
              series={[SERIES_SIGN_INS, SERIES_FAILED]}
              unit="ครั้ง"
            />
          </CardContent>
        </Card>
        <Card data-testid="org-activity">
          <CardHeader>
            <CardTitle>กิจกรรมล่าสุดในระบบ</CardTitle>
            <CardDescription>จากบันทึกการใช้งานระบบ (Audit log)</CardDescription>
          </CardHeader>
          <CardContent>
            <ActivityList
              items={security.recent}
              showActor
              selfId={selfId}
              timeZone={data.timezone}
              emptyText="ยังไม่มีกิจกรรม"
            />
          </CardContent>
        </Card>
      </div>
    </Section>
  );
}

export function DashboardView() {
  const { me } = useSession();
  const summary = useDashboardSummary();

  if (summary.isPending) return <DashboardSkeleton />;
  if (summary.isError) {
    return (
      <ErrorState
        title="ไม่สามารถโหลดแดชบอร์ดได้"
        message={summary.error.message}
        requestId={summary.error instanceof ApiError ? summary.error.requestId : null}
        onRetry={() => void summary.refetch()}
        retrying={summary.isFetching}
      />
    );
  }

  const data = summary.data;
  const selfId = me?.user.id;
  const subtitle = [
    formatLongDate(new Date(data.generated_at), data.timezone),
    data.account.job_title,
    data.account.department?.name,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <div className="space-y-8">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">
          สวัสดี, {data.account.display_name}
        </h1>
        <p className="text-muted-foreground text-sm">{subtitle}</p>
      </div>
      <PersonalSection data={data} selfId={selfId} />
      {data.organization ? <OrganizationSection org={data.organization} /> : null}
      {data.security ? (
        <SecuritySection security={data.security} data={data} selfId={selfId} />
      ) : null}
    </div>
  );
}
