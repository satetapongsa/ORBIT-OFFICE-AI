"use client";

import {
  ArrowLeft,
  Download,
  FileQuestion,
  Loader2,
  Paperclip,
  Pencil,
  Send,
  Trash2,
} from "lucide-react";
import Link from "next/link";
import { useId, useRef, useState } from "react";
import { toast } from "sonner";

import { EmptyState } from "@/components/common/empty-state";
import { ErrorState } from "@/components/common/error-state";
import { NativeSelect } from "@/components/common/native-select";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { checkFile, formatBytes, ACCEPTED_FILES } from "@/features/documents/labels";
import {
  DueLabel,
  TaskPriorityLabel,
  TaskStatusBadge,
} from "@/features/tasks/components/task-badges";
import {
  AssigneesDialog,
  DeleteTaskDialog,
  EditTaskDialog,
} from "@/features/tasks/components/task-dialogs";
import {
  useAddComment,
  useChangeStatus,
  useDeleteAttachment,
  useDeleteComment,
  useEditComment,
  useTask,
  useTaskAttachments,
  useTaskComments,
  useTaskHistory,
  useUploadAttachment,
} from "@/features/tasks/hooks/use-tasks";
import {
  STATUS_ORDER,
  TASK_EVENT_LABELS,
  TASK_FIELD_LABELS,
  TASK_STATUS_LABELS,
} from "@/features/tasks/labels";
import { formatDateTime, formatRelative } from "@/lib/format";
import { ApiError } from "@/services/api-client";
import {
  downloadAttachment,
  taskStatusSchema,
  type TaskComment,
  type TaskDetail,
  type TaskEvent,
  type TaskStatus,
} from "@/services/tasks";

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

function StatusControl({ task }: { task: TaskDetail }) {
  const id = useId();
  const change = useChangeStatus(task.id);
  const options = STATUS_ORDER.filter((s) => s !== "CANCELLED" || task.capabilities.can_cancel);
  if (!task.capabilities.can_change_status) return <TaskStatusBadge status={task.status} />;
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id} className="sr-only">
        เปลี่ยนสถานะ
      </Label>
      <NativeSelect
        id={id}
        value={task.status}
        disabled={change.isPending}
        onChange={(e) =>
          change.mutate(e.target.value as TaskStatus, {
            onSuccess: (t) =>
              toast.success(`เปลี่ยนสถานะเป็น “${TASK_STATUS_LABELS[t.status]}” แล้ว`),
            onError: (err) => toast.error(errorMessage(err, "เปลี่ยนสถานะไม่สำเร็จ")),
          })
        }
      >
        {options.map((s) => (
          <option key={s} value={s}>
            {TASK_STATUS_LABELS[s]}
          </option>
        ))}
      </NativeSelect>
    </div>
  );
}

function DetailsCard({ task }: { task: TaskDetail }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>รายละเอียดงาน</CardTitle>
      </CardHeader>
      <CardContent>
        <dl className="grid grid-cols-[7rem_minmax(0,1fr)] gap-x-3 gap-y-3 text-sm">
          <dt className="text-muted-foreground">สถานะ</dt>
          <dd>
            <StatusControl task={task} />
          </dd>
          <dt className="text-muted-foreground">ความสำคัญ</dt>
          <dd>
            <TaskPriorityLabel priority={task.priority} />
          </dd>
          <dt className="text-muted-foreground">กำหนดส่ง</dt>
          <dd>
            <DueLabel dueAt={task.due_at} overdue={task.is_overdue} />
          </dd>
          <dt className="text-muted-foreground">แผนก</dt>
          <dd>{task.department?.name ?? "—"}</dd>
          <dt className="text-muted-foreground">ผู้สร้าง</dt>
          <dd>
            <Link className="hover:underline" href={`/employees/${task.created_by.id}`}>
              {task.created_by.display_name}
            </Link>
          </dd>
          <dt className="text-muted-foreground">ผู้รับผิดชอบ</dt>
          <dd className="space-y-2">
            {task.assignees.length === 0 ? (
              <span className="text-muted-foreground">ยังไม่มี</span>
            ) : (
              <ul className="space-y-0.5" aria-label="ผู้รับผิดชอบ">
                {task.assignees.map((a) => (
                  <li key={a.id}>
                    <Link className="hover:underline" href={`/employees/${a.id}`}>
                      {a.display_name}
                    </Link>
                  </li>
                ))}
              </ul>
            )}
            {task.capabilities.can_assign ? <AssigneesDialog task={task} /> : null}
          </dd>
          <dt className="text-muted-foreground">สร้างเมื่อ</dt>
          <dd>{formatDateTime(task.created_at)}</dd>
          {task.completed_at ? (
            <>
              <dt className="text-muted-foreground">เสร็จเมื่อ</dt>
              <dd>{formatDateTime(task.completed_at)}</dd>
            </>
          ) : null}
        </dl>
      </CardContent>
    </Card>
  );
}

function CommentItem({ taskId, comment }: { taskId: string; comment: TaskComment }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(comment.body);
  const edit = useEditComment(taskId);
  const remove = useDeleteComment(taskId);
  return (
    <li className="space-y-1 py-3" data-testid="task-comment">
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm">
          <span className="font-medium">{comment.author?.display_name ?? "ผู้ใช้ที่ถูกลบ"}</span>
          <time
            className="text-muted-foreground ml-2 text-xs"
            dateTime={comment.created_at}
            title={formatDateTime(comment.created_at)}
          >
            {formatRelative(comment.created_at)}
            {comment.edited_at ? " · แก้ไขแล้ว" : ""}
          </time>
        </p>
        <div className="flex gap-1">
          {comment.can_edit && !editing ? (
            <Button
              size="icon"
              variant="ghost"
              className="size-7"
              aria-label="แก้ไขความคิดเห็น"
              onClick={() => {
                setDraft(comment.body);
                setEditing(true);
              }}
            >
              <Pencil className="size-3.5" aria-hidden />
            </Button>
          ) : null}
          {comment.can_delete ? (
            <Button
              size="icon"
              variant="ghost"
              className="text-destructive size-7"
              aria-label="ลบความคิดเห็น"
              disabled={remove.isPending}
              onClick={() =>
                remove.mutate(comment.id, {
                  onError: (e) => toast.error(errorMessage(e, "ลบความคิดเห็นไม่สำเร็จ")),
                })
              }
            >
              <Trash2 className="size-3.5" aria-hidden />
            </Button>
          ) : null}
        </div>
      </div>
      {editing ? (
        <form
          className="space-y-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (!draft.trim()) return;
            edit.mutate(
              { commentId: comment.id, body: draft.trim() },
              {
                onSuccess: () => setEditing(false),
                onError: (err) => toast.error(errorMessage(err, "แก้ไขไม่สำเร็จ")),
              },
            );
          }}
        >
          <Textarea
            aria-label="แก้ไขความคิดเห็น"
            rows={3}
            maxLength={5000}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
          />
          <div className="flex gap-2">
            <Button size="sm" type="submit" disabled={edit.isPending || !draft.trim()}>
              บันทึก
            </Button>
            <Button size="sm" type="button" variant="ghost" onClick={() => setEditing(false)}>
              ยกเลิก
            </Button>
          </div>
        </form>
      ) : (
        // Plain text: comments are user input and never rendered as HTML.
        <p className="text-sm whitespace-pre-wrap">{comment.body}</p>
      )}
    </li>
  );
}

function CommentsCard({ task }: { task: TaskDetail }) {
  const id = useId();
  const comments = useTaskComments(task.id);
  const add = useAddComment(task.id);
  const [body, setBody] = useState("");
  return (
    <Card>
      <CardHeader>
        <CardTitle>ความคิดเห็น</CardTitle>
        <CardDescription>
          ผู้สร้างและผู้รับผิดชอบจะได้รับการแจ้งเตือนเมื่อมีความคิดเห็นใหม่
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {comments.isPending ? (
          <Skeleton className="h-16 w-full" />
        ) : comments.isError ? (
          <p className="text-destructive text-sm">{comments.error.message}</p>
        ) : comments.data.length === 0 ? (
          <p className="text-muted-foreground text-sm">ยังไม่มีความคิดเห็น</p>
        ) : (
          <ul className="divide-y" aria-label="ความคิดเห็น">
            {comments.data.map((c) => (
              <CommentItem key={c.id} taskId={task.id} comment={c} />
            ))}
          </ul>
        )}
        {task.capabilities.can_comment ? (
          <form
            className="space-y-2"
            onSubmit={(e) => {
              e.preventDefault();
              const text = body.trim();
              if (!text) return;
              add.mutate(text, {
                onSuccess: () => setBody(""),
                onError: (err) => toast.error(errorMessage(err, "ส่งความคิดเห็นไม่สำเร็จ")),
              });
            }}
          >
            <Label htmlFor={id}>เพิ่มความคิดเห็น</Label>
            <Textarea
              id={id}
              rows={3}
              maxLength={5000}
              placeholder="อัปเดตความคืบหน้า หรือถามคำถามเกี่ยวกับงานนี้"
              value={body}
              onChange={(e) => setBody(e.target.value)}
            />
            <Button type="submit" size="sm" disabled={add.isPending || !body.trim()}>
              {add.isPending ? (
                <Loader2 className="animate-spin" aria-hidden />
              ) : (
                <Send aria-hidden />
              )}
              ส่ง
            </Button>
          </form>
        ) : null}
      </CardContent>
    </Card>
  );
}

function AttachmentsCard({ task }: { task: TaskDetail }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const attachments = useTaskAttachments(task.id);
  const upload = useUploadAttachment(task.id);
  const remove = useDeleteAttachment(task.id);
  const [busy, setBusy] = useState<string | null>(null);

  const onFile = (file: File | undefined) => {
    if (!file) return;
    const problem = checkFile(file);
    if (problem) {
      toast.error(problem);
      return;
    }
    upload.mutate(file, {
      onSuccess: () => toast.success(`แนบไฟล์ ${file.name} แล้ว`),
      onError: (e) => toast.error(errorMessage(e, "แนบไฟล์ไม่สำเร็จ")),
    });
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-2">
        <div className="space-y-1.5">
          <CardTitle>ไฟล์แนบ</CardTitle>
          <CardDescription>PDF, DOCX, XLSX หรือ TXT ไม่เกิน 25 MB</CardDescription>
        </div>
        {task.capabilities.can_attach ? (
          <>
            <input
              ref={inputRef}
              type="file"
              accept={ACCEPTED_FILES}
              className="sr-only"
              aria-label="เลือกไฟล์แนบ"
              onChange={(e) => {
                onFile(e.target.files?.[0]);
                e.target.value = "";
              }}
            />
            <Button
              size="sm"
              variant="outline"
              disabled={upload.isPending}
              onClick={() => inputRef.current?.click()}
            >
              {upload.isPending ? (
                <Loader2 className="animate-spin" aria-hidden />
              ) : (
                <Paperclip aria-hidden />
              )}
              แนบไฟล์
            </Button>
          </>
        ) : null}
      </CardHeader>
      <CardContent>
        {attachments.isPending ? (
          <Skeleton className="h-10 w-full" />
        ) : attachments.isError ? (
          <p className="text-destructive text-sm">{attachments.error.message}</p>
        ) : attachments.data.length === 0 ? (
          <p className="text-muted-foreground text-sm">ยังไม่มีไฟล์แนบ</p>
        ) : (
          <ul className="divide-y" aria-label="ไฟล์แนบ">
            {attachments.data.map((a) => (
              <li key={a.id} className="flex items-center justify-between gap-2 py-2">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">{a.original_filename}</p>
                  <p className="text-muted-foreground text-xs">
                    {a.file_type} · {formatBytes(a.size_bytes)} ·{" "}
                    {a.uploaded_by?.display_name ?? "ผู้ใช้ที่ถูกลบ"} ·{" "}
                    {formatRelative(a.created_at)}
                  </p>
                </div>
                <div className="flex shrink-0 gap-1">
                  <Button
                    size="icon"
                    variant="ghost"
                    aria-label={`ดาวน์โหลด ${a.original_filename}`}
                    disabled={busy === a.id}
                    onClick={async () => {
                      setBusy(a.id);
                      try {
                        await downloadAttachment(task.id, a);
                      } catch (e) {
                        toast.error(errorMessage(e, "ดาวน์โหลดไม่สำเร็จ"));
                      } finally {
                        setBusy(null);
                      }
                    }}
                  >
                    {busy === a.id ? (
                      <Loader2 className="animate-spin" aria-hidden />
                    ) : (
                      <Download aria-hidden />
                    )}
                  </Button>
                  {a.can_delete ? (
                    <Button
                      size="icon"
                      variant="ghost"
                      className="text-destructive"
                      aria-label={`ลบ ${a.original_filename}`}
                      disabled={remove.isPending}
                      onClick={() =>
                        remove.mutate(a.id, {
                          onSuccess: () => toast.success("ลบไฟล์แนบแล้ว"),
                          onError: (e) => toast.error(errorMessage(e, "ลบไฟล์แนบไม่สำเร็จ")),
                        })
                      }
                    >
                      <Trash2 aria-hidden />
                    </Button>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function describeEvent(event: TaskEvent): string {
  const label = TASK_EVENT_LABELS[event.event_type];
  switch (event.event_type) {
    case "STATUS_CHANGED": {
      const from = taskStatusSchema.safeParse(event.from_value);
      const to = taskStatusSchema.safeParse(event.to_value);
      return `${label}: ${from.success ? TASK_STATUS_LABELS[from.data] : "—"} → ${
        to.success ? TASK_STATUS_LABELS[to.data] : "—"
      }`;
    }
    case "UPDATED":
      return `${label}: ${(event.to_value ?? "")
        .split(",")
        .filter(Boolean)
        .map((f) => TASK_FIELD_LABELS[f] ?? f)
        .join(", ")}`;
    case "ASSIGNED":
    case "ATTACHMENT_ADDED":
      return `${label} ${event.to_value ?? ""}`.trim();
    case "UNASSIGNED":
    case "ATTACHMENT_REMOVED":
      return `${label} ${event.from_value ?? ""}`.trim();
    default:
      return label;
  }
}

function HistoryCard({ taskId }: { taskId: string }) {
  const history = useTaskHistory(taskId);
  return (
    <Card>
      <CardHeader>
        <CardTitle>ประวัติงาน</CardTitle>
      </CardHeader>
      <CardContent>
        {history.isPending ? (
          <Skeleton className="h-24 w-full" />
        ) : history.isError ? (
          <p className="text-destructive text-sm">{history.error.message}</p>
        ) : (
          <ol className="space-y-3" aria-label="ประวัติงาน">
            {history.data.map((e) => (
              <li key={e.id} className="text-sm" data-testid="task-event">
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

export function TaskDetailView({ id }: { id: string }) {
  const task = useTask(id);

  if (task.isPending) {
    return (
      <div className="space-y-6" aria-busy="true" aria-label="กำลังโหลดงาน">
        <Skeleton className="h-8 w-72" />
        <div className="grid gap-4 lg:grid-cols-3">
          <Skeleton className="h-80 rounded-xl lg:col-span-2" />
          <Skeleton className="h-80 rounded-xl" />
        </div>
      </div>
    );
  }
  if (task.isError) {
    if (task.error instanceof ApiError && task.error.status === 404) {
      return (
        <EmptyState
          icon={FileQuestion}
          title="ไม่พบงาน"
          description="งานนี้อาจถูกลบ หรือคุณไม่มีสิทธิ์เข้าถึง"
          action={
            <Button asChild variant="outline">
              <Link href="/tasks">กลับไปหน้ารายการงาน</Link>
            </Button>
          }
        />
      );
    }
    return (
      <ErrorState
        message={task.error.message}
        requestId={task.error instanceof ApiError ? task.error.requestId : null}
        onRetry={() => void task.refetch()}
        retrying={task.isFetching}
      />
    );
  }

  const t = task.data;
  return (
    <div className="space-y-6">
      <div className="space-y-3">
        <Link
          href="/tasks"
          className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1 text-sm"
        >
          <ArrowLeft className="size-4" aria-hidden />
          รายการงาน
        </Link>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 space-y-2">
            <h1 className="text-2xl font-semibold tracking-tight break-words">{t.title}</h1>
            <div className="flex flex-wrap items-center gap-3">
              <TaskStatusBadge status={t.status} />
              <TaskPriorityLabel priority={t.priority} />
              <DueLabel dueAt={t.due_at} overdue={t.is_overdue} />
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            {t.capabilities.can_edit ? <EditTaskDialog task={t} /> : null}
            {t.capabilities.can_delete ? <DeleteTaskDialog task={t} /> : null}
          </div>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle>รายละเอียด</CardTitle>
            </CardHeader>
            <CardContent>
              {t.description ? (
                <p className="text-sm whitespace-pre-wrap">{t.description}</p>
              ) : (
                <p className="text-muted-foreground text-sm">ไม่มีรายละเอียดเพิ่มเติม</p>
              )}
            </CardContent>
          </Card>
          <CommentsCard task={t} />
        </div>
        <div className="space-y-4">
          <DetailsCard task={t} />
          <AttachmentsCard task={t} />
          <HistoryCard taskId={t.id} />
        </div>
      </div>
    </div>
  );
}
