"use client";

import {
  Bot,
  CircleAlert,
  CircleCheck,
  Loader2,
  MessageSquarePlus,
  PanelLeft,
  Send,
  Square,
  Trash2,
} from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { toast } from "sonner";

import { EmptyState } from "@/components/common/empty-state";
import { ErrorState } from "@/components/common/error-state";
import { PageHeader } from "@/components/common/page-header";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { ActionCard } from "@/features/assistant/components/action-card";
import { MessageText } from "@/features/assistant/components/message-text";
import {
  useAiStatus,
  useChatSession,
  useChatSessions,
  useChatStream,
  useDeleteSession,
  type PendingTurn,
} from "@/features/assistant/hooks/use-assistant";
import { formatRelative } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { AiAction, ChatMessage, ChatSession, Citation } from "@/services/ai";
import { ApiError } from "@/services/api-client";

const SUGGESTIONS = [
  "งานของฉันที่ใกล้ครบกำหนดมีอะไรบ้าง",
  "นโยบายการลาพักร้อนของบริษัทเป็นอย่างไร",
  "สร้างงาน “เตรียมรายงานประจำเดือน” กำหนดส่งวันศุกร์นี้",
];

function UserBubble({ text }: { text: string }) {
  return (
    <div className="flex justify-end" data-testid="chat-user">
      <div className="bg-primary text-primary-foreground max-w-[85%] rounded-2xl rounded-br-sm px-4 py-2">
        <p className="text-sm break-words whitespace-pre-wrap">{text}</p>
      </div>
    </div>
  );
}

function Sources({ citations }: { citations: Citation[] }) {
  return (
    <div className="mt-2 border-t pt-2" data-testid="chat-sources">
      <p className="text-muted-foreground text-xs font-medium">แหล่งอ้างอิง</p>
      <ol className="mt-1 space-y-0.5 text-xs">
        {citations.map((c) => (
          <li key={c.n}>
            <span className="text-muted-foreground">[{c.n}] </span>
            <Link href={`/documents/${c.document_id}`} className="text-primary hover:underline">
              {c.title}
            </Link>
            {c.page ? <span className="text-muted-foreground"> · หน้า {c.page}</span> : null}
          </li>
        ))}
      </ol>
    </div>
  );
}

function AssistantBubble({
  text,
  streaming,
  citations = [],
}: {
  text: string;
  streaming?: boolean;
  citations?: Citation[];
}) {
  return (
    <div className="flex gap-2" data-testid="chat-assistant">
      <span className="bg-primary/10 text-primary flex size-7 shrink-0 items-center justify-center rounded-full">
        <Bot className="size-4" aria-hidden />
      </span>
      <div className="bg-muted/60 max-w-[85%] min-w-0 rounded-2xl rounded-tl-sm px-4 py-2">
        {text ? <MessageText text={text} /> : null}
        {citations.length > 0 ? <Sources citations={citations} /> : null}
        {streaming ? (
          <span
            className="text-muted-foreground inline-flex items-center gap-1 text-xs"
            role="status"
          >
            <Loader2 className="size-3 animate-spin" aria-hidden />
            กำลังตอบ…
          </span>
        ) : null}
      </div>
    </div>
  );
}

function ToolChip({ label, ok }: { label: string; ok: boolean }) {
  return (
    <p
      data-testid="chat-tool"
      className="text-muted-foreground ml-9 inline-flex items-center gap-1 text-xs"
    >
      {ok ? (
        <CircleCheck className="size-3.5 text-emerald-600" aria-hidden />
      ) : (
        <CircleAlert className="size-3.5 text-amber-600" aria-hidden />
      )}
      {label}
      {ok ? "" : " (ไม่สำเร็จ)"}
    </p>
  );
}

function StoredMessage({
  message,
  actions,
  sessionId,
}: {
  message: ChatMessage;
  actions: Map<string, AiAction>;
  sessionId: string;
}) {
  if (message.role === "user") return <UserBubble text={message.content} />;
  if (message.role === "assistant") {
    return <AssistantBubble text={message.content} citations={message.citations} />;
  }
  if (message.role === "system") {
    return (
      <div
        className="text-muted-foreground mx-auto max-w-md text-center [&_p]:text-xs"
        data-testid="chat-note"
      >
        <MessageText text={message.content} />
      </div>
    );
  }
  const action = message.action_id ? actions.get(message.action_id) : undefined;
  return (
    <div className="space-y-2">
      <ToolChip
        label={message.tool_label ?? message.tool_name ?? ""}
        ok={message.tool_ok ?? false}
      />
      {action ? (
        <div className="ml-9 max-w-md">
          <ActionCard action={action} sessionId={sessionId} />
        </div>
      ) : null}
    </div>
  );
}

function PendingView({ turn, sessionId }: { turn: PendingTurn; sessionId: string | null }) {
  const failedAfterStore = turn.error !== null && !turn.streaming;
  return (
    <>
      {failedAfterStore ? null : <UserBubble text={turn.question} />}
      {turn.tools.map((tool) => {
        const action = tool.actionId ? turn.actions.find((a) => a.id === tool.actionId) : undefined;
        return (
          <div key={tool.id} className="space-y-2">
            <ToolChip label={tool.label} ok={tool.ok} />
            {action ? (
              <div className="ml-9 max-w-md">
                <ActionCard action={action} sessionId={sessionId} />
              </div>
            ) : null}
          </div>
        );
      })}
      {turn.streaming || turn.answer ? (
        <AssistantBubble text={turn.answer} streaming={turn.streaming} />
      ) : null}
      {turn.error ? (
        <Alert variant="destructive" role="alert">
          <AlertDescription>{turn.error}</AlertDescription>
        </Alert>
      ) : null}
    </>
  );
}

function SessionList({
  sessions,
  activeId,
  onSelect,
  onNew,
  onDeleted,
}: {
  sessions: ChatSession[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDeleted: (id: string) => void;
}) {
  const remove = useDeleteSession();
  return (
    <nav aria-label="บทสนทนา" className="space-y-2">
      <Button className="w-full" variant="outline" onClick={onNew}>
        <MessageSquarePlus aria-hidden />
        บทสนทนาใหม่
      </Button>
      {sessions.length === 0 ? (
        <p className="text-muted-foreground px-2 py-4 text-center text-xs">ยังไม่มีบทสนทนา</p>
      ) : (
        <ul className="space-y-1">
          {sessions.map((s) => (
            <li key={s.id} className="group flex items-center gap-1">
              <button
                type="button"
                aria-current={s.id === activeId ? "true" : undefined}
                onClick={() => onSelect(s.id)}
                className={cn(
                  "hover:bg-muted min-w-0 flex-1 rounded-md px-2 py-1.5 text-left",
                  s.id === activeId && "bg-muted",
                )}
              >
                <span className="block truncate text-sm">{s.title}</span>
                <span className="text-muted-foreground block text-xs">
                  {formatRelative(s.last_message_at)}
                </span>
              </button>
              <Dialog>
                <DialogTrigger asChild>
                  <Button
                    size="icon"
                    variant="ghost"
                    className="size-8 shrink-0"
                    aria-label={`ลบบทสนทนา ${s.title}`}
                  >
                    <Trash2 className="size-4" aria-hidden />
                  </Button>
                </DialogTrigger>
                <DialogContent className="sm:max-w-sm">
                  <DialogHeader>
                    <DialogTitle>ลบบทสนทนานี้?</DialogTitle>
                    <DialogDescription>“{s.title}” จะหายไปจากรายการของคุณ</DialogDescription>
                  </DialogHeader>
                  <DialogFooter>
                    <DialogClose asChild>
                      <Button variant="outline">ยกเลิก</Button>
                    </DialogClose>
                    <DialogClose asChild>
                      <Button
                        variant="destructive"
                        onClick={() =>
                          remove.mutate(s.id, {
                            onSuccess: () => onDeleted(s.id),
                            onError: (e) =>
                              toast.error(e instanceof ApiError ? e.message : "ลบไม่สำเร็จ"),
                          })
                        }
                      >
                        ลบ
                      </Button>
                    </DialogClose>
                  </DialogFooter>
                </DialogContent>
              </Dialog>
            </li>
          ))}
        </ul>
      )}
    </nav>
  );
}

export function AssistantView() {
  const composerId = useId();
  const status = useAiStatus();
  const sessions = useChatSessions();
  const [activeId, setActiveId] = useState<string | null>(null);
  const [showList, setShowList] = useState(false);
  const params = useSearchParams();
  // "สรุปด้วยผู้ช่วย AI" links pre-fill the composer; nothing is sent until the user does.
  const [draft, setDraft] = useState(() => (params.get("prompt") ?? "").slice(0, 4000));
  const detail = useChatSession(activeId);
  const chat = useChatStream(activeId, setActiveId);
  const endRef = useRef<HTMLDivElement>(null);

  const enabled = status.data?.enabled ?? false;
  const maxChars = status.data?.max_message_chars ?? 4000;
  const streaming = chat.pending?.streaming ?? false;

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: "end" });
  }, [detail.data, chat.pending]);

  const submit = (text: string) => {
    const question = text.trim();
    if (!question || streaming || !enabled || question.length > maxChars) return;
    setDraft("");
    void chat.send(question);
  };
  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit(draft);
    }
  };
  const startNew = () => {
    chat.clear();
    setActiveId(null);
    setShowList(false);
  };

  if (status.isPending) {
    return (
      <div className="space-y-4" aria-busy="true" aria-label="กำลังโหลดผู้ช่วย AI">
        <Skeleton className="h-8 w-56" />
        <Skeleton className="h-96 w-full rounded-xl" />
      </div>
    );
  }
  if (status.isError) {
    return (
      <ErrorState
        message={status.error.message}
        requestId={status.error instanceof ApiError ? status.error.requestId : null}
        onRetry={() => void status.refetch()}
        retrying={status.isFetching}
      />
    );
  }

  const actions = new Map((detail.data?.actions ?? []).map((a) => [a.id, a]));
  const messages = detail.data?.messages ?? [];
  const empty = messages.length === 0 && chat.pending === null;

  return (
    <>
      <PageHeader
        title="ผู้ช่วย AI"
        description="ถามเรื่องงานของคุณ ให้ช่วยสรุปหรือเตรียมงานใหม่ ผู้ช่วยเห็นเฉพาะข้อมูลที่คุณมีสิทธิ์ และจะไม่เปลี่ยนแปลงข้อมูลจนกว่าคุณจะกดยืนยัน"
        actions={
          enabled ? (
            <Badge variant="secondary" title="โมเดลที่ใช้งาน">
              {status.data.model}
            </Badge>
          ) : null
        }
      />

      {!enabled ? (
        <Alert className="mb-4">
          <AlertTitle>ยังไม่ได้ตั้งค่าผู้ให้บริการ AI</AlertTitle>
          <AlertDescription>
            ผู้ดูแลระบบต้องกำหนด AI_CHAT_PROVIDER และค่าที่เกี่ยวข้องก่อน จึงจะส่งข้อความได้
            บทสนทนาเดิมยังเปิดดูได้ตามปกติ
          </AlertDescription>
        </Alert>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-[16rem_minmax(0,1fr)]">
        <div className="lg:hidden">
          <Button
            variant="outline"
            size="sm"
            aria-expanded={showList}
            onClick={() => setShowList((v) => !v)}
          >
            <PanelLeft aria-hidden />
            บทสนทนาทั้งหมด
          </Button>
        </div>
        <aside className={cn(showList ? "block" : "hidden", "lg:block")}>
          {sessions.isPending ? (
            <Skeleton className="h-40 w-full" />
          ) : sessions.isError ? (
            <p className="text-destructive text-sm">{sessions.error.message}</p>
          ) : (
            <SessionList
              sessions={sessions.data.items}
              activeId={activeId}
              onSelect={(id) => {
                chat.clear();
                setActiveId(id);
                setShowList(false);
              }}
              onNew={startNew}
              onDeleted={(id) => {
                if (id === activeId) startNew();
              }}
            />
          )}
        </aside>

        <Card className="flex min-h-[28rem] flex-col py-0">
          <CardContent
            className="flex-1 space-y-4 overflow-y-auto px-4 py-4 lg:max-h-[calc(100vh-18rem)]"
            aria-live="polite"
            aria-label="ข้อความในบทสนทนา"
          >
            {activeId !== null && detail.isPending ? (
              <Skeleton className="h-24 w-full" />
            ) : detail.isError ? (
              <p className="text-destructive text-sm">{detail.error.message}</p>
            ) : empty ? (
              <EmptyState
                icon={Bot}
                title="เริ่มคุยกับผู้ช่วย AI"
                description="ผู้ช่วยค้นหางานของคุณ สรุปสิ่งที่ต้องทำ และเตรียมงานใหม่ให้คุณยืนยันได้"
                action={
                  enabled && (status.data.tools.length ?? 0) > 0 ? (
                    <div className="flex flex-wrap justify-center gap-2">
                      {SUGGESTIONS.map((s) => (
                        <Button key={s} size="sm" variant="outline" onClick={() => submit(s)}>
                          {s}
                        </Button>
                      ))}
                    </div>
                  ) : null
                }
              />
            ) : (
              <>
                {messages.map((m) => (
                  <StoredMessage
                    key={m.id}
                    message={m}
                    actions={actions}
                    sessionId={activeId ?? ""}
                  />
                ))}
                {chat.pending ? <PendingView turn={chat.pending} sessionId={activeId} /> : null}
              </>
            )}
            <div ref={endRef} />
          </CardContent>
          <form
            className="border-t p-3"
            onSubmit={(e) => {
              e.preventDefault();
              submit(draft);
            }}
          >
            <label htmlFor={composerId} className="sr-only">
              ข้อความถึงผู้ช่วย AI
            </label>
            <Textarea
              id={composerId}
              rows={2}
              value={draft}
              maxLength={maxChars}
              disabled={!enabled}
              placeholder={
                enabled
                  ? "พิมพ์คำถาม แล้วกด Enter เพื่อส่ง (Shift+Enter ขึ้นบรรทัดใหม่)"
                  : "ยังใช้งานไม่ได้"
              }
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={onKeyDown}
            />
            <div className="mt-2 flex items-center justify-between gap-2">
              <span className="text-muted-foreground text-xs tabular-nums">
                {draft.length.toLocaleString("th-TH")} / {maxChars.toLocaleString("th-TH")}
              </span>
              {streaming ? (
                <Button type="button" size="sm" variant="outline" onClick={chat.stop}>
                  <Square aria-hidden />
                  หยุด
                </Button>
              ) : (
                <Button type="submit" size="sm" disabled={!enabled || !draft.trim()}>
                  <Send aria-hidden />
                  ส่ง
                </Button>
              )}
            </div>
          </form>
        </Card>
      </div>
    </>
  );
}
