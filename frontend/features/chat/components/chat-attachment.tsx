"use client";

import { Download, FileText, ImageOff, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { formatBytes } from "@/features/documents/labels";
import { cn } from "@/lib/utils";
import { ApiError } from "@/services/api-client";
import { downloadChatFile, fetchChatImage, type ChatAttachment } from "@/services/chat";

/** Loads an image through the API (participants only) and shows it from a blob: URL. */
function useImageUrl(id: string, enabled: boolean): { url: string | null; failed: boolean } {
  const [state, setState] = useState<{ id: string; url: string | null; failed: boolean }>({
    id,
    url: null,
    failed: false,
  });
  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    let objectUrl: string | null = null;
    fetchChatImage(id, controller.signal)
      .then((blob) => {
        objectUrl = URL.createObjectURL(blob);
        setState({ id, url: objectUrl, failed: false });
      })
      .catch(() => {
        if (!controller.signal.aborted) setState({ id, url: null, failed: true });
      });
    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [id, enabled]);
  return state.id === id ? state : { url: null, failed: false };
}

async function download(attachment: ChatAttachment) {
  try {
    await downloadChatFile(attachment);
  } catch (error) {
    toast.error(error instanceof ApiError ? error.message : "ดาวน์โหลดไฟล์ไม่สำเร็จ");
  }
}

function ChatImage({ attachment, mine }: { attachment: ChatAttachment; mine: boolean }) {
  const { url, failed } = useImageUrl(attachment.id, true);
  const [open, setOpen] = useState(false);
  if (failed) {
    return (
      <span className="flex items-center gap-2 px-2 py-3 text-xs opacity-80">
        <ImageOff className="size-4" aria-hidden />
        แสดงรูปไม่สำเร็จ
      </span>
    );
  }
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        disabled={!url}
        className={cn(
          "block max-w-full overflow-hidden rounded-xl",
          mine ? "bg-primary-foreground/10" : "bg-background/60",
        )}
        aria-label={`ดูรูป ${attachment.original_filename}`}
      >
        {url ? (
          // eslint-disable-next-line @next/next/no-img-element -- blob: URL, not optimisable
          <img
            src={url}
            alt={attachment.original_filename}
            className="block max-h-64 w-auto max-w-full object-contain"
            data-testid="chat-image"
          />
        ) : (
          <span className="flex h-40 w-56 items-center justify-center">
            <Loader2 className="size-5 animate-spin opacity-60" aria-label="กำลังโหลดรูป" />
          </span>
        )}
      </button>
      {open && url ? (
        <Dialog open onOpenChange={(value) => (!value ? setOpen(false) : undefined)}>
          <DialogContent className="max-h-[95dvh] sm:max-w-4xl">
            <DialogHeader>
              <DialogTitle className="truncate pr-6">{attachment.original_filename}</DialogTitle>
              <DialogDescription>{formatBytes(attachment.size_bytes)}</DialogDescription>
            </DialogHeader>
            {/* eslint-disable-next-line @next/next/no-img-element -- blob: URL */}
            <img
              src={url}
              alt={attachment.original_filename}
              className="mx-auto max-h-[75dvh] w-auto max-w-full rounded-lg object-contain"
            />
            <div className="flex justify-end">
              <Button variant="outline" onClick={() => void download(attachment)}>
                <Download aria-hidden />
                ดาวน์โหลด
              </Button>
            </div>
          </DialogContent>
        </Dialog>
      ) : null}
    </>
  );
}

/** A file or image inside a chat bubble. `pending` = still uploading (nothing to open yet). */
export function ChatAttachmentView({
  attachment,
  mine,
  pending = false,
}: {
  attachment: ChatAttachment;
  mine: boolean;
  pending?: boolean;
}) {
  if (attachment.is_image && !pending) return <ChatImage attachment={attachment} mine={mine} />;
  return (
    <div
      className={cn(
        "flex min-w-0 items-center gap-3 rounded-xl px-3 py-2",
        mine ? "bg-primary-foreground/10" : "bg-background/70",
      )}
      data-testid="chat-file"
    >
      <span
        className={cn(
          "flex size-9 shrink-0 items-center justify-center rounded-lg",
          mine ? "bg-primary-foreground/15" : "bg-primary/10 text-primary",
        )}
      >
        {pending ? (
          <Loader2 className="size-4 animate-spin" aria-hidden />
        ) : (
          <FileText className="size-4" aria-hidden />
        )}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-medium">{attachment.original_filename}</span>
        <span className="block text-[11px] opacity-75">
          {pending
            ? "กำลังอัปโหลด…"
            : `${attachment.file_type} · ${formatBytes(attachment.size_bytes)}`}
        </span>
      </span>
      {!pending ? (
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="size-8 shrink-0"
          onClick={() => void download(attachment)}
          aria-label={`ดาวน์โหลด ${attachment.original_filename}`}
          title="ดาวน์โหลด"
        >
          <Download className="size-4" aria-hidden />
        </Button>
      ) : null}
    </div>
  );
}
