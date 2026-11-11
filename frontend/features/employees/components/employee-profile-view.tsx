"use client";

import { ArrowLeft, Mail, Phone, UserX } from "lucide-react";
import Link from "next/link";

import { EmptyState } from "@/components/common/empty-state";
import { ErrorState } from "@/components/common/error-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useSession } from "@/features/auth/hooks/use-session";
import {
  ActiveToggleDialog,
  EditAccountDialog,
  RolesDialog,
} from "@/features/employees/components/account-dialogs";
import { HrProfileCard } from "@/features/employees/components/hr-profile-card";
import { useEmployee } from "@/features/employees/hooks/use-employees";
import { EMPLOYMENT_STATUS_LABELS, initials } from "@/features/employees/labels";
import { formatDateTime } from "@/lib/format";
import { ApiError } from "@/services/api-client";
import type { EmployeeProfile } from "@/services/employees";

function AccountCard({ employee }: { employee: EmployeeProfile }) {
  const account = employee.account;
  const caps = employee.capabilities;
  if (!account) return null;
  return (
    <Card data-testid="account-card">
      <CardHeader>
        <CardTitle>บัญชีผู้ใช้</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <dl className="grid grid-cols-[9rem_minmax(0,1fr)] gap-x-3 gap-y-2 text-sm">
          <dt className="text-muted-foreground">สถานะบัญชี</dt>
          <dd>{employee.is_active ? "ใช้งานได้" : "ถูกระงับ"}</dd>
          <dt className="text-muted-foreground">สถานะการจ้างงาน</dt>
          <dd>{EMPLOYMENT_STATUS_LABELS[account.employment_status]}</dd>
          <dt className="text-muted-foreground">บทบาท</dt>
          <dd className="flex flex-wrap gap-1">
            {account.roles.length === 0 ? (
              <span className="text-muted-foreground">ไม่มีบทบาท</span>
            ) : (
              account.roles.map((r) => (
                <Badge key={r.id} variant="secondary">
                  {r.name}
                </Badge>
              ))
            )}
          </dd>
          <dt className="text-muted-foreground">เข้าสู่ระบบล่าสุด</dt>
          <dd>{account.last_login_at ? formatDateTime(account.last_login_at) : "ยังไม่เคย"}</dd>
          <dt className="text-muted-foreground">สร้างบัญชีเมื่อ</dt>
          <dd>{formatDateTime(account.created_at)}</dd>
        </dl>
        {caps.can_edit_account || caps.can_manage_roles || caps.can_change_active ? (
          <div className="flex flex-wrap gap-2 border-t pt-4">
            {caps.can_edit_account ? <EditAccountDialog employee={employee} /> : null}
            {caps.can_manage_roles ? <RolesDialog employee={employee} /> : null}
            {caps.can_change_active ? <ActiveToggleDialog employee={employee} /> : null}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

export function EmployeeProfileView({ id }: { id: string }) {
  const { me } = useSession();
  const employee = useEmployee(id);

  if (employee.isPending) {
    return (
      <div className="space-y-6" aria-busy="true" aria-label="กำลังโหลดข้อมูลพนักงาน">
        <Skeleton className="h-20 w-full max-w-xl" />
        <Skeleton className="h-72 rounded-xl" />
      </div>
    );
  }
  if (employee.isError) {
    if (employee.error instanceof ApiError && employee.error.status === 404) {
      return (
        <EmptyState
          icon={UserX}
          title="ไม่พบพนักงาน"
          description="บัญชีนี้อาจถูกระงับ หรือคุณไม่มีสิทธิ์ดูข้อมูล"
          action={
            <Button asChild variant="outline">
              <Link href="/employees">กลับไปหน้าศูนย์พนักงาน</Link>
            </Button>
          }
        />
      );
    }
    return (
      <ErrorState
        message={employee.error.message}
        requestId={employee.error instanceof ApiError ? employee.error.requestId : null}
        onRetry={() => void employee.refetch()}
        retrying={employee.isFetching}
      />
    );
  }

  const e = employee.data;
  const isSelf = me?.user.id === e.id;
  return (
    <div className="space-y-6">
      <Link
        href="/employees"
        className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1 text-sm"
      >
        <ArrowLeft className="size-4" aria-hidden />
        ศูนย์พนักงาน
      </Link>
      <div className="flex flex-wrap items-center gap-4">
        <span
          aria-hidden
          className="bg-primary/10 text-primary flex size-16 items-center justify-center rounded-full text-xl font-semibold"
        >
          {initials(e.first_name, e.last_name)}
        </span>
        <div className="min-w-0 space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight break-words">{e.display_name}</h1>
          <p className="text-muted-foreground text-sm">
            {[e.job_title, e.department?.name].filter(Boolean).join(" · ") || "ไม่ระบุตำแหน่ง"}
          </p>
          <div className="flex flex-wrap gap-1.5">
            <Badge variant="outline">รหัส {e.employee_code}</Badge>
            {isSelf ? <Badge variant="secondary">คุณ</Badge> : null}
            {!e.is_active ? <Badge variant="destructive">บัญชีถูกระงับ</Badge> : null}
          </div>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle>ข้อมูลติดต่อที่ทำงาน</CardTitle>
            </CardHeader>
            <CardContent>
              <dl className="grid grid-cols-[9rem_minmax(0,1fr)] gap-x-3 gap-y-2 text-sm">
                <dt className="text-muted-foreground">อีเมล</dt>
                <dd className="flex min-w-0 items-center gap-1">
                  <Mail className="text-muted-foreground size-3.5 shrink-0" aria-hidden />
                  <a className="truncate hover:underline" href={`mailto:${e.email}`}>
                    {e.email}
                  </a>
                </dd>
                <dt className="text-muted-foreground">เบอร์โทร</dt>
                <dd className="flex items-center gap-1">
                  {e.phone_work ? (
                    <>
                      <Phone className="text-muted-foreground size-3.5" aria-hidden />
                      <a className="hover:underline" href={`tel:${e.phone_work}`}>
                        {e.phone_work}
                      </a>
                    </>
                  ) : (
                    "—"
                  )}
                </dd>
                <dt className="text-muted-foreground">แผนก</dt>
                <dd>{e.department?.name ?? "—"}</dd>
                <dt className="text-muted-foreground">หัวหน้าแผนก</dt>
                <dd>
                  {e.department_manager ? (
                    <Link
                      className="hover:underline"
                      href={`/employees/${e.department_manager.id}`}
                    >
                      {e.department_manager.display_name}
                    </Link>
                  ) : (
                    "—"
                  )}
                </dd>
              </dl>
            </CardContent>
          </Card>
          {e.capabilities.can_view_hr ? <HrProfileCard employee={e} isSelf={isSelf} /> : null}
        </div>
        <div className="space-y-4">
          <AccountCard employee={e} />
        </div>
      </div>
    </div>
  );
}
