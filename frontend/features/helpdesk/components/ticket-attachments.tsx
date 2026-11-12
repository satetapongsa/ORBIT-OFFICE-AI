"use client";

import {
  Download,
  Eye,
  FileText,
  Image as ImageIcon,
  Loader2,
  Lock,
  Paperclip,
  Trash2,
} from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { formatBytes } from "@/features/documents/labels";
import {
  useDeleteTicketAttachment,
  useTicketAttachments,
  useUploadTicketAttachment,
} from "@/features/helpdesk/hooks/use-tickets";
import { TICKET_ACCEPTED_FILES, checkTicketFile } from "@/features/helpdesk/labels";
import { formatRelative } from "@/lib/format";
import { cn } from "@/lib/utils";
import { ApiError } from "@/services/api-client";
import {
  downloadTicketAttachment,
  fetchTicketImage,
  type TicketAttachment,
  type TicketDetail,
} from "@/services/tickets";

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

const isImage = (a: TicketAttachment) => a.file_type === "PNG" || a.file_type === "JPEG";

/** Shows a screenshot from a blob: URL (never from the API URL directly). */
function ImagePreview({
  ticketId,
  attachment,
  onClose,
}: {
  ticketId: string;
  attachment: TicketAttachment;
  onClose: () => void;
}) {
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let objectUrl: string | null = null;
    let cancelled = false;
    fetchTicketImage(ticketId, attachment.id)
      .then((blob) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setUrl(objectUrl);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [ticketId, attachment.id]);

  return (
    <Dialog open onOpenChange={(open) => (open ? null : onClose())}>
      <DialogContent className="sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle className="break-all">{attachment.original_filename}</DialogTitle>
          <DialogDescription>
            {formatBytes(attachment.size_bytes)} ·{" "}
            {attachment.uploaded_by?.display_name ?? "ผู้ใช้ที่ถูกลบ"}
          </DialogDescription>
        </DialogHeader>
        {failed ? (
          <p className="text-destructive text-sm">แสดงรูปไม่สำเร็จ</p>
        ) : url ? (
          // eslint-disable-next-line @next/next/no-img-element -- a private blob, not a site asset
          <img
            src={url}
            alt={attachment.original_filename}
            className="max-h-[70vh] w-full rounded-md object-contain"
          />
        ) : (
          <Skeleton className="h-64 w-full" aria-label="กำลังโหลดรูป" />
        )}
      </DialogContent>
    </Dialog>
  );
}

export function TicketAttachmentsCard({ ticket }: { ticket: TicketDetail }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const internalId = useId();
  const attachments = useTicketAttachments(ticket.id);
  const upload = useUploadTicketAttachment(ticket.id);
  const remove = useDeleteTicketAttachment(ticket.id);
  const [internal, setInternal] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [preview, setPreview] = useState<TicketAttachment | null>(null);
  const { can_attach: canAttach, can_attach_internal: canAttachInternal } = ticket.capabilities;

  const onFiles = async (files: FileList | null) => {
    for (const file of Array.from(files ?? [])) {
      const problem = checkTicketFile(file);
      if (problem) {
        toast.error(`${file.name}: ${problem}`);
        continue;
      }
      try {
        await upload.mutateAsync({ file, internal: canAttachInternal && internal });
        toast.success(`แนบไฟล์ ${file.name} แล้ว`);
      } catch (e) {
        toast.error(`${file.name}: ${errorMessage(e, "แนบไฟล์ไม่สำเร็จ")}`);
      }
    }
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-2">
        <div className="space-y-1.5">
          <CardTitle>ไฟล์แนบ</CardTitle>
          <CardDescription>
            ภาพหน้าจอ (PNG, JPG) หรือ PDF, DOCX, XLSX, TXT ไม่เกิน 25 MB
          </CardDescription>
        </div>
        {canAttach ? (
          <>
            <input
              ref={inputRef}
              type="file"
              multiple
              accept={TICKET_ACCEPTED_FILES}
              className="sr-only"
              aria-label="เลือกไฟล์แนบ"
              onChange={(e) => {
                void onFiles(e.target.files);
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
      <CardContent className="space-y-3">
        {canAttachInternal ? (
          <label htmlFor={internalId} className="flex items-center gap-2 text-sm">
            <input
              id={internalId}
              type="checkbox"
              className="size-4"
              checked={internal}
              onChange={(e) => setInternal(e.target.checked)}
            />
            แนบเป็นไฟล์ภายใน (ผู้แจ้งไม่เห็น)
          </label>
        ) : null}
        {attachments.isPending ? (
          <Skeleton className="h-10 w-full" />
        ) : attachments.isError ? (
          <p className="text-destructive text-sm">{attachments.error.message}</p>
        ) : attachments.data.length === 0 ? (
          <p className="text-muted-foreground text-sm">
            {canAttach
              ? "ยังไม่มีไฟล์แนบ แนบภาพหน้าจอช่วยให้ทีมไอทีแก้ปัญหาได้เร็วขึ้น"
              : "ไม่มีไฟล์แนบ"}
          </p>
        ) : (
          <ul className="divide-y" aria-label="ไฟล์แนบ">
            {attachments.data.map((a) => {
              const Icon = isImage(a) ? ImageIcon : FileText;
              return (
                <li
                  key={a.id}
                  data-testid="ticket-attachment"
                  className={cn(
                    "flex items-center justify-between gap-2 py-2",
                    a.is_internal && "rounded-md bg-amber-50/60 px-2",
                  )}
                >
                  <div className="flex min-w-0 items-start gap-2">
                    <Icon className="text-muted-foreground mt-0.5 size-4 shrink-0" aria-hidden />
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">{a.original_filename}</p>
                      <p className="text-muted-foreground flex flex-wrap items-center gap-x-1 text-xs">
                        {a.is_internal ? (
                          <span className="inline-flex items-center gap-0.5 font-medium text-amber-800">
                            <Lock className="size-3" aria-hidden />
                            ภายใน ·
                          </span>
                        ) : null}
                        {formatBytes(a.size_bytes)} ·{" "}
                        {a.uploaded_by?.display_name ?? "ผู้ใช้ที่ถูกลบ"} ·{" "}
                        {formatRelative(a.created_at)}
                      </p>
                    </div>
                  </div>
                  <div className="flex shrink-0 gap-1">
                    {isImage(a) ? (
                      <Button
                        size="icon"
                        variant="ghost"
                        aria-label={`ดูรูป ${a.original_filename}`}
                        onClick={() => setPreview(a)}
                      >
                        <Eye aria-hidden />
                      </Button>
                    ) : null}
                    <Button
                      size="icon"
                      variant="ghost"
                      aria-label={`ดาวน์โหลด ${a.original_filename}`}
                      disabled={busy === a.id}
                      onClick={async () => {
                        setBusy(a.id);
                        try {
                          await downloadTicketAttachment(ticket.id, a);
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
              );
            })}
          </ul>
        )}
      </CardContent>
      {preview ? (
        <ImagePreview ticketId={ticket.id} attachment={preview} onClose={() => setPreview(null)} />
      ) : null}
    </Card>
  );
}
