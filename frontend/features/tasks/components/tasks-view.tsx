"use client";

import {
  ChevronLeft,
  ChevronRight,
  ListChecks,
  MessageSquare,
  Paperclip,
  Search,
  SearchX,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useId, useState } from "react";

import { EmptyState } from "@/components/common/empty-state";
import { ErrorState } from "@/components/common/error-state";
import { NativeSelect } from "@/components/common/native-select";
import { PageHeader } from "@/components/common/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { useSession } from "@/features/auth/hooks/use-session";
import {
  DueLabel,
  TaskPriorityLabel,
  TaskStatusBadge,
} from "@/features/tasks/components/task-badges";
import { CreateTaskDialog } from "@/features/tasks/components/task-dialogs";
import { useTaskList } from "@/features/tasks/hooks/use-tasks";
import { TASK_PRIORITY_LABELS, TASK_STATUS_LABELS } from "@/features/tasks/labels";
import { cn } from "@/lib/utils";
import { ApiError } from "@/services/api-client";
import {
  taskPrioritySchema,
  taskStatusSchema,
  type TaskListItem,
  type TaskListParams,
  type TaskPriority,
  type TaskScope,
  type TaskSort,
  type TaskStatus,
} from "@/services/tasks";

const PAGE_SIZE = 20;

function useDebounced<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

function TaskRow({ task }: { task: TaskListItem }) {
  const names = task.assignees.map((a) => a.display_name);
  return (
    <li data-testid="task-row">
      <Link
        href={`/tasks/${task.id}`}
        className="hover:bg-muted/50 focus-visible:ring-ring/50 grid gap-2 rounded-lg px-3 py-3 outline-none focus-visible:ring-2 md:grid-cols-[minmax(0,1fr)_8.5rem_7rem_9rem] md:items-center md:gap-4"
      >
        <div className="min-w-0">
          <p className="truncate font-medium">{task.title}</p>
          <p className="text-muted-foreground flex flex-wrap items-center gap-x-2 text-xs">
            <span className="truncate">
              {names.length > 0 ? names.slice(0, 3).join(", ") : "ยังไม่มีผู้รับผิดชอบ"}
              {names.length > 3 ? ` +${names.length - 3}` : ""}
            </span>
            {task.comment_count > 0 ? (
              <span className="inline-flex items-center gap-0.5">
                <MessageSquare className="size-3" aria-hidden />
                <span className="sr-only">ความคิดเห็น</span>
                {task.comment_count}
              </span>
            ) : null}
            {task.attachment_count > 0 ? (
              <span className="inline-flex items-center gap-0.5">
                <Paperclip className="size-3" aria-hidden />
                <span className="sr-only">ไฟล์แนบ</span>
                {task.attachment_count}
              </span>
            ) : null}
          </p>
        </div>
        <div>
          <TaskStatusBadge status={task.status} />
        </div>
        <div>
          <TaskPriorityLabel priority={task.priority} />
        </div>
        <div className="md:text-right">
          <DueLabel dueAt={task.due_at} overdue={task.is_overdue} />
        </div>
      </Link>
    </li>
  );
}

const SCOPES: { value: TaskScope; label: string; permission?: string[] }[] = [
  { value: "all", label: "ทั้งหมดที่ฉันเห็น" },
  { value: "assigned", label: "มอบหมายให้ฉัน" },
  { value: "created", label: "ที่ฉันสร้าง" },
  {
    value: "department",
    label: "งานของแผนก",
    permission: ["tasks:read_department", "tasks:manage_department", "tasks:manage_all"],
  },
];

export function TasksView() {
  const { has, me } = useSession();
  const ids = { q: useId(), status: useId(), priority: useId(), sort: useId() };
  const [scope, setScope] = useState<TaskScope>("assigned");
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<TaskStatus | "open" | "">("open");
  const [priority, setPriority] = useState<TaskPriority | "">("");
  const [overdue, setOverdue] = useState(false);
  const [sort, setSort] = useState<TaskSort>("due");
  const [page, setPage] = useState(1);
  const q = useDebounced(search.trim());

  const scopes = SCOPES.filter((s) => !s.permission || s.permission.some((p) => has(p))).filter(
    (s) => s.value !== "department" || me?.user.department,
  );

  const params: TaskListParams = {
    scope,
    q: q || undefined,
    status: status && status !== "open" ? status : undefined,
    openOnly: status === "open",
    priority: priority || undefined,
    overdue,
    sort,
    page,
    pageSize: PAGE_SIZE,
  };
  const list = useTaskList(params);
  const totalPages = list.data ? Math.max(1, Math.ceil(list.data.total / PAGE_SIZE)) : 1;
  const filtered = Boolean(q || status || priority || overdue);
  const resetPage = () => setPage(1);

  return (
    <>
      <PageHeader
        title="จัดการงาน"
        description="ติดตามงานของคุณและทีม ระบบแสดงเฉพาะงานที่คุณมีสิทธิ์เห็น"
        actions={has("tasks:create") ? <CreateTaskDialog /> : null}
      />

      <div role="tablist" aria-label="ขอบเขตงาน" className="mb-4 flex flex-wrap gap-1.5">
        {scopes.map((s) => (
          <Button
            key={s.value}
            role="tab"
            aria-selected={scope === s.value}
            size="sm"
            variant={scope === s.value ? "default" : "outline"}
            onClick={() => {
              setScope(s.value);
              resetPage();
            }}
          >
            {s.label}
          </Button>
        ))}
      </div>

      <div
        role="search"
        className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-[minmax(0,1fr)_10rem_9rem_9rem_auto] lg:items-end"
      >
        <div className="space-y-1.5 sm:col-span-2 lg:col-span-1">
          <Label htmlFor={ids.q}>ค้นหา</Label>
          <div className="relative">
            <Search
              className="text-muted-foreground absolute top-1/2 left-2.5 size-4 -translate-y-1/2"
              aria-hidden
            />
            <Input
              id={ids.q}
              type="search"
              placeholder="ชื่องานหรือรายละเอียด"
              className="pl-8"
              value={search}
              maxLength={200}
              onChange={(e) => {
                setSearch(e.target.value);
                resetPage();
              }}
            />
          </div>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor={ids.status}>สถานะ</Label>
          <NativeSelect
            id={ids.status}
            value={status}
            onChange={(e) => {
              setStatus(e.target.value as TaskStatus | "open" | "");
              resetPage();
            }}
          >
            <option value="open">ยังไม่เสร็จ</option>
            <option value="">ทุกสถานะ</option>
            {taskStatusSchema.options.map((s) => (
              <option key={s} value={s}>
                {TASK_STATUS_LABELS[s]}
              </option>
            ))}
          </NativeSelect>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor={ids.priority}>ความสำคัญ</Label>
          <NativeSelect
            id={ids.priority}
            value={priority}
            onChange={(e) => {
              setPriority(e.target.value as TaskPriority | "");
              resetPage();
            }}
          >
            <option value="">ทั้งหมด</option>
            {taskPrioritySchema.options.map((p) => (
              <option key={p} value={p}>
                {TASK_PRIORITY_LABELS[p]}
              </option>
            ))}
          </NativeSelect>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor={ids.sort}>เรียงตาม</Label>
          <NativeSelect
            id={ids.sort}
            value={sort}
            onChange={(e) => setSort(e.target.value as TaskSort)}
          >
            <option value="due">กำหนดส่งใกล้สุด</option>
            <option value="priority">ความสำคัญ</option>
            <option value="updated">อัปเดตล่าสุด</option>
            <option value="created">สร้างล่าสุด</option>
          </NativeSelect>
        </div>
        <Button
          type="button"
          variant={overdue ? "default" : "outline"}
          aria-pressed={overdue}
          className={cn(overdue && "bg-red-700 hover:bg-red-700/90")}
          onClick={() => {
            setOverdue((v) => !v);
            resetPage();
          }}
        >
          เลยกำหนด
        </Button>
      </div>

      {list.isPending ? (
        <Card>
          <CardContent className="space-y-3" aria-busy="true" aria-label="กำลังโหลดรายการงาน">
            {Array.from({ length: 5 }, (_, i) => (
              <Skeleton key={i} className="h-14 w-full" />
            ))}
          </CardContent>
        </Card>
      ) : list.isError ? (
        <ErrorState
          message={list.error.message}
          requestId={list.error instanceof ApiError ? list.error.requestId : null}
          onRetry={() => void list.refetch()}
          retrying={list.isFetching}
        />
      ) : list.data.items.length === 0 ? (
        filtered && status !== "open" ? (
          <EmptyState
            icon={SearchX}
            title="ไม่พบงานที่ตรงกับเงื่อนไข"
            description="ลองเปลี่ยนคำค้นหรือตัวกรอง"
          />
        ) : (
          <EmptyState
            icon={ListChecks}
            title={status === "open" ? "ไม่มีงานค้างในมุมมองนี้" : "ยังไม่มีงาน"}
            description={
              has("tasks:create")
                ? "สร้างงานใหม่ หรือเลือก “ทุกสถานะ” เพื่อดูงานที่เสร็จแล้ว"
                : "เมื่อมีผู้มอบหมายงานให้คุณ งานจะแสดงที่นี่"
            }
          />
        )
      ) : (
        <Card className="py-2">
          <CardContent className="px-2">
            <div className="text-muted-foreground hidden grid-cols-[minmax(0,1fr)_8.5rem_7rem_9rem] gap-4 px-3 py-2 text-xs font-medium md:grid">
              <span>งาน / ผู้รับผิดชอบ</span>
              <span>สถานะ</span>
              <span>ความสำคัญ</span>
              <span className="text-right">กำหนดส่ง</span>
            </div>
            <ul className="divide-y" aria-label="รายการงาน">
              {list.data.items.map((task) => (
                <TaskRow key={task.id} task={task} />
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {list.data && list.data.total > 0 ? (
        <nav
          aria-label="เลื่อนหน้า"
          className="mt-4 flex items-center justify-between gap-2 text-sm"
        >
          <span className="text-muted-foreground">
            ทั้งหมด {list.data.total.toLocaleString("th-TH")} งาน
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
