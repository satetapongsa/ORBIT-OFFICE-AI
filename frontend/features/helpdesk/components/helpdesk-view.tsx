"use client";

import { ChevronLeft, ChevronRight, Headset, Search, SearchX } from "lucide-react";
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
import { CreateTicketDialog } from "@/features/helpdesk/components/create-ticket-dialog";
import { TicketStatusBadge } from "@/features/helpdesk/components/ticket-badges";
import { useTicketList } from "@/features/helpdesk/hooks/use-tickets";
import { TICKET_CATEGORY_LABELS, TICKET_STATUS_LABELS } from "@/features/helpdesk/labels";
import { TaskPriorityLabel } from "@/features/tasks/components/task-badges";
import { formatRelative } from "@/lib/format";
import { ApiError } from "@/services/api-client";
import {
  ticketCategorySchema,
  ticketStatusSchema,
  type TicketCategory,
  type TicketListItem,
  type TicketListParams,
  type TicketScope,
  type TicketSort,
  type TicketStatus,
} from "@/services/tickets";

const PAGE_SIZE = 20;

function useDebounced<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

function TicketRow({ ticket, showRequester }: { ticket: TicketListItem; showRequester: boolean }) {
  return (
    <li data-testid="ticket-row">
      <Link
        href={`/helpdesk/${ticket.id}`}
        className="hover:bg-muted/50 focus-visible:ring-ring/50 grid gap-2 rounded-lg px-3 py-3 outline-none focus-visible:ring-2 md:grid-cols-[minmax(0,1fr)_10rem_7rem_8rem] md:items-center md:gap-4"
      >
        <div className="min-w-0">
          <p className="truncate font-medium">
            <span className="text-muted-foreground mr-2 font-mono text-xs">
              {ticket.ticket_number}
            </span>
            {ticket.title}
          </p>
          <p className="text-muted-foreground truncate text-xs">
            {TICKET_CATEGORY_LABELS[ticket.category]}
            {showRequester ? ` · ผู้แจ้ง ${ticket.requester.display_name}` : ""}
            {" · "}
            {ticket.assignee
              ? `ผู้รับผิดชอบ ${ticket.assignee.display_name}`
              : "ยังไม่มีผู้รับเรื่อง"}
          </p>
        </div>
        <div>
          <TicketStatusBadge status={ticket.status} />
        </div>
        <div>
          <TaskPriorityLabel priority={ticket.priority} />
        </div>
        <div className="text-muted-foreground text-xs md:text-right">
          <time dateTime={ticket.updated_at}>{formatRelative(ticket.updated_at)}</time>
        </div>
      </Link>
    </li>
  );
}

const STAFF_SCOPES: { value: TicketScope; label: string }[] = [
  { value: "all", label: "ทั้งหมด" },
  { value: "assigned", label: "มอบหมายให้ฉัน" },
  { value: "unassigned", label: "ยังไม่มีผู้รับเรื่อง" },
  { value: "mine", label: "ที่ฉันแจ้ง" },
];

export function HelpdeskView() {
  const { has } = useSession();
  const isStaff = has("tickets:read_all");
  const ids = { q: useId(), status: useId(), category: useId(), sort: useId() };
  const [scope, setScope] = useState<TicketScope>(isStaff ? "all" : "mine");
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<TicketStatus | "open" | "">("open");
  const [category, setCategory] = useState<TicketCategory | "">("");
  const [sort, setSort] = useState<TicketSort>("updated");
  const [page, setPage] = useState(1);
  const q = useDebounced(search.trim());

  const params: TicketListParams = {
    scope,
    q: q || undefined,
    status: status && status !== "open" ? status : undefined,
    openOnly: status === "open",
    category: category || undefined,
    sort,
    page,
    pageSize: PAGE_SIZE,
  };
  const list = useTicketList(params);
  const totalPages = list.data ? Math.max(1, Math.ceil(list.data.total / PAGE_SIZE)) : 1;
  const filtered = Boolean(q || (status && status !== "open") || category);
  const resetPage = () => setPage(1);

  return (
    <>
      <PageHeader
        title="แจ้งปัญหาไอที"
        description={
          isStaff
            ? "รับเรื่อง มอบหมาย และติดตามปัญหาไอทีของทุกคนในองค์กร"
            : "แจ้งปัญหาคอมพิวเตอร์ เครือข่าย โปรแกรม หรือบัญชีผู้ใช้ และติดตามความคืบหน้า"
        }
        actions={has("tickets:create") ? <CreateTicketDialog /> : null}
      />

      {isStaff ? (
        <div role="tablist" aria-label="ขอบเขตรายการ" className="mb-4 flex flex-wrap gap-1.5">
          {STAFF_SCOPES.map((s) => (
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
      ) : null}

      <div
        role="search"
        className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-[minmax(0,1fr)_11rem_11rem_10rem] lg:items-end"
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
              placeholder="เลขที่หรือเรื่อง"
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
              setStatus(e.target.value as TicketStatus | "open" | "");
              resetPage();
            }}
          >
            <option value="open">ยังไม่เสร็จ</option>
            <option value="">ทุกสถานะ</option>
            {ticketStatusSchema.options.map((s) => (
              <option key={s} value={s}>
                {TICKET_STATUS_LABELS[s]}
              </option>
            ))}
          </NativeSelect>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor={ids.category}>หมวด</Label>
          <NativeSelect
            id={ids.category}
            value={category}
            onChange={(e) => {
              setCategory(e.target.value as TicketCategory | "");
              resetPage();
            }}
          >
            <option value="">ทุกหมวด</option>
            {ticketCategorySchema.options.map((c) => (
              <option key={c} value={c}>
                {TICKET_CATEGORY_LABELS[c]}
              </option>
            ))}
          </NativeSelect>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor={ids.sort}>เรียงตาม</Label>
          <NativeSelect
            id={ids.sort}
            value={sort}
            onChange={(e) => setSort(e.target.value as TicketSort)}
          >
            <option value="updated">อัปเดตล่าสุด</option>
            <option value="created">แจ้งล่าสุด</option>
            <option value="priority">ความเร่งด่วน</option>
          </NativeSelect>
        </div>
      </div>

      {list.isPending ? (
        <Card>
          <CardContent className="space-y-3" aria-busy="true" aria-label="กำลังโหลดรายการ">
            {Array.from({ length: 4 }, (_, i) => (
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
        filtered || q ? (
          <EmptyState
            icon={SearchX}
            title="ไม่พบรายการที่ตรงกับเงื่อนไข"
            description="ลองเปลี่ยนคำค้นหรือตัวกรอง"
          />
        ) : (
          <EmptyState
            icon={Headset}
            title={status === "open" ? "ไม่มีเรื่องค้างในมุมมองนี้" : "ยังไม่มีรายการแจ้งปัญหา"}
            description={
              isStaff
                ? "เรื่องใหม่จะแสดงที่นี่ และทีมไอทีจะได้รับการแจ้งเตือน"
                : "มีปัญหาการใช้งานไอที กด “แจ้งปัญหาใหม่” หรือบอกผู้ช่วย AI ให้แจ้งแทนได้"
            }
          />
        )
      ) : (
        <Card className="py-2">
          <CardContent className="px-2">
            <div className="text-muted-foreground hidden grid-cols-[minmax(0,1fr)_10rem_7rem_8rem] gap-4 px-3 py-2 text-xs font-medium md:grid">
              <span>เรื่อง</span>
              <span>สถานะ</span>
              <span>ความเร่งด่วน</span>
              <span className="text-right">อัปเดต</span>
            </div>
            <ul className="divide-y" aria-label="รายการแจ้งปัญหา">
              {list.data.items.map((ticket) => (
                <TicketRow key={ticket.id} ticket={ticket} showRequester={isStaff} />
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
            ทั้งหมด {list.data.total.toLocaleString("th-TH")} รายการ
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
