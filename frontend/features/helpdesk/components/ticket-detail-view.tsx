"use client";

import { ArrowLeft, FileQuestion, Loader2, Lock, Send } from "lucide-react";
import Link from "next/link";
import { useId, useState } from "react";
import { toast } from "sonner";

import { EmptyState } from "@/components/common/empty-state";
import { ErrorState } from "@/components/common/error-state";
import { NativeSelect } from "@/components/common/native-select";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { TicketAttachmentsCard } from "@/features/helpdesk/components/ticket-attachments";
import { TicketStatusBadge } from "@/features/helpdesk/components/ticket-badges";
import {
  useAddTicketComment,
  useAssignTicket,
  useChangeTicketStatus,
  useTicket,
  useTicketAssignees,
  useTicketComments,
  useTicketHistory,
  useUpdateTicket,
} from "@/features/helpdesk/hooks/use-tickets";
import {
  REQUESTER_ACTIONS,
  TICKET_CATEGORY_LABELS,
  TICKET_EVENT_LABELS,
  TICKET_STATUS_LABELS,
} from "@/features/helpdesk/labels";
import { TaskPriorityLabel } from "@/features/tasks/components/task-badges";
import { TASK_PRIORITY_LABELS } from "@/features/tasks/labels";
import { formatDateTime, formatRelative } from "@/lib/format";
import { cn } from "@/lib/utils";
import { ApiError } from "@/services/api-client";
import { taskPrioritySchema, type TaskPriority } from "@/services/tasks";
import {
  ticketCategorySchema,
  ticketStatusSchema,
  type TicketCategory,
  type TicketDetail,
  type TicketEvent,
  type TicketStatus,
} from "@/services/tickets";

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

/** IT staff pick any status; requesters get plain-language buttons for what they may do. */
function StatusActions({ ticket }: { ticket: TicketDetail }) {
  const id = useId();
  const change = useChangeTicketStatus(ticket.id);
  const allowed = ticket.capabilities.allowed_statuses;
  const run = (status: TicketStatus) =>
    change.mutate(status, {
      onSuccess: (t) => toast.success(`สถานะ: ${TICKET_STATUS_LABELS[t.status]}`),
      onError: (err) => toast.error(errorMessage(err, "เปลี่ยนสถานะไม่สำเร็จ")),
    });

  if (ticket.capabilities.can_manage) {
    return (
      <div className="space-y-1.5">
        <Label htmlFor={id} className="sr-only">
          เปลี่ยนสถานะ
        </Label>
        <NativeSelect
          id={id}
          value={ticket.status}
          disabled={change.isPending}
          onChange={(e) => run(e.target.value as TicketStatus)}
        >
          {ticketStatusSchema.options
            .filter((s) => s === ticket.status || allowed.includes(s))
            .map((s) => (
              <option key={s} value={s}>
                {TICKET_STATUS_LABELS[s]}
              </option>
            ))}
        </NativeSelect>
      </div>
    );
  }
  if (allowed.length === 0) return <TicketStatusBadge status={ticket.status} />;
  return (
    <div className="flex flex-col items-start gap-2">
      <TicketStatusBadge status={ticket.status} />
      {allowed.map((s) => (
        <Button
          key={s}
          size="sm"
          variant={s === "CLOSED" ? "default" : "outline"}
          disabled={change.isPending}
          onClick={() => run(s)}
        >
          {REQUESTER_ACTIONS[s] ?? TICKET_STATUS_LABELS[s]}
        </Button>
      ))}
    </div>
  );
}

function AssigneeControl({ ticket }: { ticket: TicketDetail }) {
  const id = useId();
  const staff = useTicketAssignees(ticket.capabilities.can_assign);
  const assign = useAssignTicket(ticket.id);
  if (!ticket.capabilities.can_assign) {
    return <span>{ticket.assignee?.display_name ?? "ยังไม่มีผู้รับเรื่อง"}</span>;
  }
  const options = staff.data ?? [];
  const current = ticket.assignee;
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id} className="sr-only">
        ผู้รับผิดชอบ
      </Label>
      <NativeSelect
        id={id}
        value={current?.id ?? ""}
        disabled={assign.isPending || staff.isPending}
        onChange={(e) =>
          assign.mutate(e.target.value || null, {
            onSuccess: (t) =>
              toast.success(
                t.assignee ? `มอบหมายให้ ${t.assignee.display_name} แล้ว` : "ถอนการมอบหมายแล้ว",
              ),
            onError: (err) => toast.error(errorMessage(err, "มอบหมายไม่สำเร็จ")),
          })
        }
      >
        <option value="">— ยังไม่มีผู้รับเรื่อง —</option>
        {current && !options.some((o) => o.id === current.id) ? (
          <option value={current.id}>{current.display_name}</option>
        ) : null}
        {options.map((o) => (
          <option key={o.id} value={o.id}>
            {o.display_name}
          </option>
        ))}
      </NativeSelect>
    </div>
  );
}

function ClassificationControls({ ticket }: { ticket: TicketDetail }) {
  const ids = { category: useId(), priority: useId() };
  const update = useUpdateTicket(ticket.id);
  const save = (input: { category?: TicketCategory; priority?: TaskPriority }) =>
    update.mutate(input, {
      onSuccess: () => toast.success("บันทึกแล้ว"),
      onError: (err) => toast.error(errorMessage(err, "บันทึกไม่สำเร็จ")),
    });
  return (
    <>
      <dt className="text-muted-foreground">
        <Label htmlFor={ids.category} className="font-normal">
          หมวด
        </Label>
      </dt>
      <dd>
        <NativeSelect
          id={ids.category}
          value={ticket.category}
          disabled={update.isPending}
          onChange={(e) => save({ category: e.target.value as TicketCategory })}
        >
          {ticketCategorySchema.options.map((c) => (
            <option key={c} value={c}>
              {TICKET_CATEGORY_LABELS[c]}
            </option>
          ))}
        </NativeSelect>
      </dd>
      <dt className="text-muted-foreground">
        <Label htmlFor={ids.priority} className="font-normal">
          ความเร่งด่วน
        </Label>
      </dt>
      <dd>
        <NativeSelect
          id={ids.priority}
          value={ticket.priority}
          disabled={update.isPending}
          onChange={(e) => save({ priority: e.target.value as TaskPriority })}
        >
          {taskPrioritySchema.options.map((p) => (
            <option key={p} value={p}>
              {TASK_PRIORITY_LABELS[p]}
            </option>
          ))}
        </NativeSelect>
      </dd>
    </>
  );
}

function DetailsCard({ ticket }: { ticket: TicketDetail }) {
  const manage = ticket.capabilities.can_manage;
  return (
    <Card>
      <CardHeader>
        <CardTitle>ข้อมูลการแจ้ง</CardTitle>
      </CardHeader>
      <CardContent>
        <dl className="grid grid-cols-[7rem_minmax(0,1fr)] items-start gap-x-3 gap-y-3 text-sm">
          <dt className="text-muted-foreground">สถานะ</dt>
          <dd>
            <StatusActions ticket={ticket} />
          </dd>
          <dt className="text-muted-foreground">ผู้รับผิดชอบ</dt>
          <dd>
            <AssigneeControl ticket={ticket} />
          </dd>
          {manage ? (
            <ClassificationControls ticket={ticket} />
          ) : (
            <>
              <dt className="text-muted-foreground">หมวด</dt>
              <dd>{TICKET_CATEGORY_LABELS[ticket.category]}</dd>
              <dt className="text-muted-foreground">ความเร่งด่วน</dt>
              <dd>
                <TaskPriorityLabel priority={ticket.priority} />
              </dd>
            </>
          )}
          <dt className="text-muted-foreground">ผู้แจ้ง</dt>
          <dd>{ticket.requester.display_name}</dd>
          <dt className="text-muted-foreground">แจ้งเมื่อ</dt>
          <dd>{formatDateTime(ticket.created_at)}</dd>
          {ticket.resolved_at ? (
            <>
              <dt className="text-muted-foreground">แก้ไขเมื่อ</dt>
              <dd>{formatDateTime(ticket.resolved_at)}</dd>
            </>
          ) : null}
          {ticket.closed_at ? (
            <>
              <dt className="text-muted-foreground">ปิดเรื่องเมื่อ</dt>
              <dd>{formatDateTime(ticket.closed_at)}</dd>
            </>
          ) : null}
        </dl>
      </CardContent>
    </Card>
  );
}

function ConversationCard({ ticket }: { ticket: TicketDetail }) {
  const ids = { body: useId(), internal: useId() };
  const comments = useTicketComments(ticket.id);
  const add = useAddTicketComment(ticket.id);
  const [body, setBody] = useState("");
  const [internal, setInternal] = useState(false);
  const staff = ticket.capabilities.can_comment_internal;
  return (
    <Card>
      <CardHeader>
        <CardTitle>การสนทนา</CardTitle>
        <CardDescription>
          {staff
            ? "ข้อความปกติผู้แจ้งจะเห็นและได้รับแจ้งเตือน บันทึกภายในเห็นเฉพาะทีมไอที"
            : "สอบถามหรือให้ข้อมูลเพิ่มเติมกับทีมไอทีได้ที่นี่"}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {comments.isPending ? (
          <Skeleton className="h-16 w-full" />
        ) : comments.isError ? (
          <p className="text-destructive text-sm">{comments.error.message}</p>
        ) : comments.data.length === 0 ? (
          <p className="text-muted-foreground text-sm">ยังไม่มีข้อความ</p>
        ) : (
          <ul className="space-y-3" aria-label="การสนทนา">
            {comments.data.map((c) => (
              <li
                key={c.id}
                data-testid="ticket-comment"
                className={cn(
                  "rounded-lg border p-3",
                  c.is_internal && "border-amber-300 bg-amber-50/60",
                )}
              >
                <p className="flex flex-wrap items-center gap-x-2 text-sm">
                  <span className="font-medium">{c.author?.display_name ?? "ผู้ใช้ที่ถูกลบ"}</span>
                  {c.is_internal ? (
                    <span className="inline-flex items-center gap-1 text-xs font-medium text-amber-800">
                      <Lock className="size-3" aria-hidden />
                      บันทึกภายใน
                    </span>
                  ) : null}
                  <time
                    className="text-muted-foreground text-xs"
                    dateTime={c.created_at}
                    title={formatDateTime(c.created_at)}
                  >
                    {formatRelative(c.created_at)}
                  </time>
                </p>
                {/* Plain text: messages are user input and never rendered as HTML. */}
                <p className="mt-1 text-sm whitespace-pre-wrap">{c.body}</p>
              </li>
            ))}
          </ul>
        )}
        {ticket.capabilities.can_comment ? (
          <form
            className="space-y-2"
            onSubmit={(e) => {
              e.preventDefault();
              const text = body.trim();
              if (!text) return;
              add.mutate(
                { body: text, internal: staff && internal },
                {
                  onSuccess: () => {
                    setBody("");
                    setInternal(false);
                  },
                  onError: (err) => toast.error(errorMessage(err, "ส่งข้อความไม่สำเร็จ")),
                },
              );
            }}
          >
            <Label htmlFor={ids.body}>{internal ? "บันทึกภายใน" : "ตอบกลับ"}</Label>
            <Textarea
              id={ids.body}
              rows={3}
              maxLength={5000}
              value={body}
              onChange={(e) => setBody(e.target.value)}
            />
            <div className="flex flex-wrap items-center gap-3">
              <Button type="submit" size="sm" disabled={add.isPending || !body.trim()}>
                {add.isPending ? (
                  <Loader2 className="animate-spin" aria-hidden />
                ) : (
                  <Send aria-hidden />
                )}
                ส่ง
              </Button>
              {staff ? (
                <label htmlFor={ids.internal} className="flex items-center gap-2 text-sm">
                  <input
                    id={ids.internal}
                    type="checkbox"
                    className="size-4"
                    checked={internal}
                    onChange={(e) => setInternal(e.target.checked)}
                  />
                  บันทึกภายใน (ผู้แจ้งไม่เห็น)
                </label>
              ) : null}
            </div>
          </form>
        ) : null}
      </CardContent>
    </Card>
  );
}

function describeEvent(event: TicketEvent): string {
  const label = TICKET_EVENT_LABELS[event.event_type];
  switch (event.event_type) {
    case "STATUS_CHANGED": {
      const from = ticketStatusSchema.safeParse(event.from_value);
      const to = ticketStatusSchema.safeParse(event.to_value);
      return `${label}: ${from.success ? TICKET_STATUS_LABELS[from.data] : "—"} → ${
        to.success ? TICKET_STATUS_LABELS[to.data] : "—"
      }`;
    }
    case "CATEGORY_CHANGED": {
      const to = ticketCategorySchema.safeParse(event.to_value);
      return `${label}: ${to.success ? TICKET_CATEGORY_LABELS[to.data] : "—"}`;
    }
    case "PRIORITY_CHANGED": {
      const to = taskPrioritySchema.safeParse(event.to_value);
      return `${label}: ${to.success ? TASK_PRIORITY_LABELS[to.data] : "—"}`;
    }
    case "ASSIGNED":
      return `${label} ${event.to_value ?? ""}`.trim();
    case "UNASSIGNED":
      return `${label} ${event.from_value ?? ""}`.trim();
    case "COMMENTED":
      return event.is_internal ? "เพิ่มบันทึกภายใน" : label;
    case "ATTACHMENT_ADDED":
      return `${event.is_internal ? "แนบไฟล์ภายใน" : label} ${event.to_value ?? ""}`.trim();
    case "ATTACHMENT_REMOVED":
      return `${label} ${event.from_value ?? ""}`.trim();
    default:
      return label;
  }
}

function HistoryCard({ ticketId }: { ticketId: string }) {
  const history = useTicketHistory(ticketId);
  return (
    <Card>
      <CardHeader>
        <CardTitle>ประวัติ</CardTitle>
      </CardHeader>
      <CardContent>
        {history.isPending ? (
          <Skeleton className="h-24 w-full" />
        ) : history.isError ? (
          <p className="text-destructive text-sm">{history.error.message}</p>
        ) : (
          <ol className="space-y-3" aria-label="ประวัติการแจ้งปัญหา">
            {history.data.map((e) => (
              <li key={e.id} className="text-sm" data-testid="ticket-event">
                <p>{describeEvent(e)}</p>
                <p className="text-muted-foreground text-xs">
                  {e.actor?.display_name ?? "ระบบ"} ·{" "}
                  <time dateTime={e.created_at} title={formatDateTime(e.created_at)}>
                    {formatRelative(e.created_at)}
                  </time>
                </p>
              </li>
            ))}
          </ol>
        )}
      </CardContent>
    </Card>
  );
}

export function TicketDetailView({ id }: { id: string }) {
  const ticket = useTicket(id);

  if (ticket.isPending) {
    return (
      <div className="space-y-6" aria-busy="true" aria-label="กำลังโหลดรายการแจ้งปัญหา">
        <Skeleton className="h-8 w-72" />
        <div className="grid gap-4 lg:grid-cols-3">
          <Skeleton className="h-80 rounded-xl lg:col-span-2" />
          <Skeleton className="h-80 rounded-xl" />
        </div>
      </div>
    );
  }
  if (ticket.isError) {
    if (ticket.error instanceof ApiError && ticket.error.status === 404) {
      return (
        <EmptyState
          icon={FileQuestion}
          title="ไม่พบรายการแจ้งปัญหา"
          description="รายการนี้อาจถูกลบ หรือคุณไม่มีสิทธิ์เข้าถึง"
          action={
            <Button asChild variant="outline">
              <Link href="/helpdesk">กลับไปหน้ารายการ</Link>
            </Button>
          }
        />
      );
    }
    return (
      <ErrorState
        message={ticket.error.message}
        requestId={ticket.error instanceof ApiError ? ticket.error.requestId : null}
        onRetry={() => void ticket.refetch()}
        retrying={ticket.isFetching}
      />
    );
  }

  const t = ticket.data;
  return (
    <div className="space-y-6">
      <div className="space-y-3">
        <Link
          href="/helpdesk"
          className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1 text-sm"
        >
          <ArrowLeft className="size-4" aria-hidden />
          รายการแจ้งปัญหา
        </Link>
        <div className="min-w-0 space-y-2">
          <p className="text-muted-foreground font-mono text-sm">{t.ticket_number}</p>
          <h1 className="text-2xl font-semibold tracking-tight break-words">{t.title}</h1>
          <div className="flex flex-wrap items-center gap-3">
            <TicketStatusBadge status={t.status} />
            <TaskPriorityLabel priority={t.priority} />
            <span className="text-muted-foreground text-xs">
              {TICKET_CATEGORY_LABELS[t.category]}
            </span>
          </div>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle>รายละเอียดปัญหา</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm whitespace-pre-wrap">{t.description}</p>
            </CardContent>
          </Card>
          <ConversationCard ticket={t} />
        </div>
        <div className="space-y-4">
          <DetailsCard ticket={t} />
          <TicketAttachmentsCard ticket={t} />
          <HistoryCard ticketId={t.id} />
        </div>
      </div>
    </div>
  );
}
