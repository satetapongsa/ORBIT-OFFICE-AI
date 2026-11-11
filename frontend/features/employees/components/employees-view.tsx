"use client";

import { Building2, ChevronLeft, ChevronRight, Mail, Phone, Search, Users } from "lucide-react";
import Link from "next/link";
import { useEffect, useId, useState } from "react";

import { EmptyState } from "@/components/common/empty-state";
import { ErrorState } from "@/components/common/error-state";
import { NativeSelect } from "@/components/common/native-select";
import { PageHeader } from "@/components/common/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { useSession } from "@/features/auth/hooks/use-session";
import {
  CreateEmployeeDialog,
  DepartmentDialog,
} from "@/features/employees/components/account-dialogs";
import { useDepartmentsFull, useEmployeeList } from "@/features/employees/hooks/use-employees";
import { initials } from "@/features/employees/labels";
import { ApiError } from "@/services/api-client";
import type { Employee } from "@/services/employees";

const PAGE_SIZE = 24;

function useDebounced<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

function EmployeeCard({ employee }: { employee: Employee }) {
  return (
    <li data-testid="employee-card">
      <Card className="h-full py-4">
        <CardContent className="flex gap-3 px-4">
          <span
            aria-hidden
            className="bg-primary/10 text-primary flex size-11 shrink-0 items-center justify-center rounded-full text-sm font-semibold"
          >
            {initials(employee.first_name, employee.last_name)}
          </span>
          <div className="min-w-0 flex-1 space-y-1">
            <Link
              href={`/employees/${employee.id}`}
              className="block truncate font-medium hover:underline"
            >
              {employee.display_name}
            </Link>
            <p className="text-muted-foreground truncate text-xs">
              {[employee.job_title, employee.department?.name].filter(Boolean).join(" · ") ||
                "ไม่ระบุตำแหน่ง"}
            </p>
            {!employee.is_active ? <Badge variant="outline">บัญชีถูกระงับ</Badge> : null}
            <p className="flex min-w-0 items-center gap-1 text-xs">
              <Mail className="text-muted-foreground size-3 shrink-0" aria-hidden />
              <a href={`mailto:${employee.email}`} className="truncate hover:underline">
                {employee.email}
              </a>
            </p>
            {employee.phone_work ? (
              <p className="flex items-center gap-1 text-xs">
                <Phone className="text-muted-foreground size-3" aria-hidden />
                <a href={`tel:${employee.phone_work}`} className="hover:underline">
                  {employee.phone_work}
                </a>
              </p>
            ) : null}
          </div>
        </CardContent>
      </Card>
    </li>
  );
}

function Directory({
  department,
  onDepartment,
}: {
  department: string;
  onDepartment: (id: string) => void;
}) {
  const { has } = useSession();
  const ids = { q: useId(), department: useId() };
  const departments = useDepartmentsFull();
  const [search, setSearch] = useState("");
  const [inactive, setInactive] = useState(false);
  const [page, setPage] = useState(1);
  const q = useDebounced(search.trim());
  const list = useEmployeeList({
    q: q || undefined,
    departmentId: department || undefined,
    includeInactive: inactive,
    page,
    pageSize: PAGE_SIZE,
  });
  const totalPages = list.data ? Math.max(1, Math.ceil(list.data.total / PAGE_SIZE)) : 1;

  return (
    <>
      <div
        role="search"
        className="mb-4 grid gap-3 sm:grid-cols-[minmax(0,1fr)_14rem_auto] sm:items-end"
      >
        <div className="space-y-1.5">
          <Label htmlFor={ids.q}>ค้นหาพนักงาน</Label>
          <div className="relative">
            <Search
              className="text-muted-foreground absolute top-1/2 left-2.5 size-4 -translate-y-1/2"
              aria-hidden
            />
            <Input
              id={ids.q}
              type="search"
              placeholder="ชื่อ ตำแหน่ง อีเมล หรือรหัสพนักงาน"
              className="pl-8"
              value={search}
              maxLength={100}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
            />
          </div>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor={ids.department}>แผนก</Label>
          <NativeSelect
            id={ids.department}
            value={department}
            onChange={(e) => {
              onDepartment(e.target.value);
              setPage(1);
            }}
          >
            <option value="">ทุกแผนก</option>
            {(departments.data ?? []).map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </NativeSelect>
        </div>
        {has("users:read") ? (
          <Button
            type="button"
            variant={inactive ? "default" : "outline"}
            aria-pressed={inactive}
            onClick={() => {
              setInactive((v) => !v);
              setPage(1);
            }}
          >
            รวมบัญชีที่ถูกระงับ
          </Button>
        ) : null}
      </div>

      {list.isPending ? (
        <ul
          className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3"
          aria-busy="true"
          aria-label="กำลังโหลด"
        >
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} className="h-32 rounded-xl" />
          ))}
        </ul>
      ) : list.isError ? (
        <ErrorState
          message={list.error.message}
          requestId={list.error instanceof ApiError ? list.error.requestId : null}
          onRetry={() => void list.refetch()}
          retrying={list.isFetching}
        />
      ) : list.data.items.length === 0 ? (
        <EmptyState icon={Users} title="ไม่พบพนักงาน" description="ลองเปลี่ยนคำค้นหรือแผนก" />
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3" aria-label="รายชื่อพนักงาน">
          {list.data.items.map((e) => (
            <EmployeeCard key={e.id} employee={e} />
          ))}
        </ul>
      )}

      {list.data && list.data.total > 0 ? (
        <nav
          aria-label="เลื่อนหน้า"
          className="mt-4 flex items-center justify-between gap-2 text-sm"
        >
          <span className="text-muted-foreground">
            ทั้งหมด {list.data.total.toLocaleString("th-TH")} คน
          </span>
          {totalPages > 1 ? (
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1}
                onClick={() => setPage((p) => p - 1)}
              >
                <ChevronLeft aria-hidden />
                ก่อนหน้า
              </Button>
              <span className="text-muted-foreground tabular-nums">
                หน้า {page} / {totalPages}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => p + 1)}
              >
                ถัดไป
                <ChevronRight aria-hidden />
              </Button>
            </div>
          ) : null}
        </nav>
      ) : null}
    </>
  );
}

function Departments({ onOpen }: { onOpen: (id: string) => void }) {
  const { has } = useSession();
  const departments = useDepartmentsFull();
  const canManage = has("departments:manage");

  if (departments.isPending) {
    return <Skeleton className="h-48 w-full rounded-xl" />;
  }
  if (departments.isError) {
    return (
      <ErrorState
        message={departments.error.message}
        requestId={departments.error instanceof ApiError ? departments.error.requestId : null}
        onRetry={() => void departments.refetch()}
        retrying={departments.isFetching}
      />
    );
  }
  return (
    <div className="space-y-4">
      {canManage ? (
        <div className="flex justify-end">
          <DepartmentDialog />
        </div>
      ) : null}
      {departments.data.length === 0 ? (
        <EmptyState icon={Building2} title="ยังไม่มีแผนก" />
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3" aria-label="รายชื่อแผนก">
          {departments.data.map((d) => (
            <li key={d.id} data-testid="department-card">
              <Card className="h-full py-4">
                <CardContent className="space-y-2 px-4">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="truncate font-medium">{d.name}</p>
                      <p className="text-muted-foreground text-xs">รหัส {d.code}</p>
                    </div>
                    {canManage ? <DepartmentDialog department={d} /> : null}
                  </div>
                  {d.description ? (
                    <p className="text-muted-foreground line-clamp-2 text-sm">{d.description}</p>
                  ) : null}
                  <Button variant="outline" size="sm" onClick={() => onOpen(d.id)}>
                    <Users aria-hidden />
                    พนักงาน {d.member_count.toLocaleString("th-TH")} คน
                  </Button>
                </CardContent>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function EmployeesView() {
  const { has } = useSession();
  const [tab, setTab] = useState<"people" | "departments">("people");
  const [department, setDepartment] = useState("");

  return (
    <>
      <PageHeader
        title="ศูนย์พนักงาน"
        description="สมุดรายชื่อและช่องทางติดต่อที่ทำงานของเพื่อนร่วมงาน ข้อมูลส่วนบุคคลแสดงเฉพาะผู้ที่มีสิทธิ์"
        actions={has("users:create") ? <CreateEmployeeDialog /> : null}
      />
      <div role="tablist" aria-label="มุมมอง" className="mb-4 flex gap-1.5">
        <Button
          role="tab"
          size="sm"
          aria-selected={tab === "people"}
          variant={tab === "people" ? "default" : "outline"}
          onClick={() => setTab("people")}
        >
          <Users aria-hidden />
          พนักงาน
        </Button>
        <Button
          role="tab"
          size="sm"
          aria-selected={tab === "departments"}
          variant={tab === "departments" ? "default" : "outline"}
          onClick={() => setTab("departments")}
        >
          <Building2 aria-hidden />
          แผนก
        </Button>
      </div>
      {tab === "people" ? (
        <Directory department={department} onDepartment={setDepartment} />
      ) : (
        <Departments
          onOpen={(id) => {
            setDepartment(id);
            setTab("people");
          }}
        />
      )}
    </>
  );
}
