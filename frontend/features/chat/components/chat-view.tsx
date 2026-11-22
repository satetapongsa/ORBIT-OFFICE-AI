"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Loader2, MessagesSquare, Send, Users } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { toast } from "sonner";

import { EmptyState } from "@/components/common/empty-state";
import { ErrorState } from "@/components/common/error-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useSession } from "@/features/auth/hooks/use-session";
import { formatDateTime, formatRelative } from "@/lib/format";
import { cn } from "@/lib/utils";
import { ApiError } from "@/services/api-client";
import {
  chatQueryKeys,
  listConversations,
  listMessages,
  markConversationRead,
  MESSAGE_MAX_CHARS,
  sendMessage,
  startConversation,
  type ChatMessage,
  type Conversation,
} from "@/services/chat";

/** New messages appear by polling: simple, and works on hosts without WebSockets. */
const THREAD_POLL_MS = 4_000;
const LIST_POLL_MS = 10_000;
const PAGE_SIZE = 50;

function initials(name: string): string {
  const parts = name.trim().split(/\s+/);
  return ((parts[0]?.[0] ?? "") + (parts[1]?.[0] ?? "")).toUpperCase();
}

function errorText(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

function Avatar({ name, className }: { name: string; className?: string }) {
  return (
    <span
      aria-hidden
      className={cn(
        "bg-primary/10 text-primary flex size-10 shrink-0 items-center justify-center rounded-full text-sm font-semibold",
        className,
      )}
    >
      {initials(name)}
    </span>
  );
}

function ConversationItem({
  conversation,
  active,
  myId,
  onSelect,
}: {
  conversation: Conversation;
  active: boolean;
  myId: string | undefined;
  onSelect: () => void;
}) {
  const last = conversation.last_message;
  const preview = last
    ? `${last.sender_id === myId ? "คุณ: " : ""}${last.body}`
    : "ยังไม่มีข้อความ";
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-current={active ? "true" : undefined}
      className={cn(
        "flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left transition-colors",
        active ? "bg-accent" : "hover:bg-accent/60",
      )}
    >
      <Avatar name={conversation.other.display_name} />
      <span className="min-w-0 flex-1">
        <span className="flex items-baseline justify-between gap-2">
          <span className="truncate text-sm font-medium">{conversation.other.display_name}</span>
          {conversation.last_message_at ? (
            <span className="text-muted-foreground shrink-0 text-xs">
              {formatRelative(conversation.last_message_at)}
            </span>
          ) : null}
        </span>
        <span className="flex items-center justify-between gap-2">
          <span
            className={cn(
              "truncate text-xs",
              conversation.unread_count ? "text-foreground font-medium" : "text-muted-foreground",
            )}
          >
            {preview}
          </span>
          {conversation.unread_count ? (
            <Badge className="h-5 min-w-5 shrink-0 justify-center px-1.5 text-[11px]">
              {conversation.unread_count > 99 ? "99+" : conversation.unread_count}
            </Badge>
          ) : null}
        </span>
      </span>
    </button>
  );
}

function Thread({ conversation, onBack }: { conversation: Conversation; onBack: () => void }) {
  const { me } = useSession();
  const myId = me?.user.id;
  const client = useQueryClient();
  const [older, setOlder] = useState<ChatMessage[]>([]);
  const [hasMoreOlder, setHasMoreOlder] = useState<boolean | null>(null);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [draft, setDraft] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  const latest = useQuery({
    queryKey: chatQueryKeys.messages(conversation.id),
    queryFn: ({ signal }) => listMessages(conversation.id, { limit: PAGE_SIZE }, signal),
    refetchInterval: THREAD_POLL_MS,
  });

  const messages = useMemo(() => {
    const seen = new Set<string>();
    return [...older, ...(latest.data?.items ?? [])].filter((m) =>
      seen.has(m.id) ? false : (seen.add(m.id), true),
    );
  }, [older, latest.data]);
  const newestId = messages.at(-1)?.id;
  const canLoadOlder = hasMoreOlder ?? latest.data?.has_more ?? false;

  // Mark as read whenever a new message shows up, then refresh the badges.
  useEffect(() => {
    if (!newestId) return;
    void markConversationRead(conversation.id)
      .then(() =>
        Promise.all([
          client.invalidateQueries({ queryKey: chatQueryKeys.unread }),
          client.invalidateQueries({ queryKey: chatQueryKeys.conversations }),
        ]),
      )
      .catch(() => undefined);
  }, [newestId, conversation.id, client]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [newestId]);

  const send = useMutation({
    mutationFn: (body: string) => sendMessage(conversation.id, body),
    onSuccess: async () => {
      setDraft("");
      await Promise.all([
        client.invalidateQueries({ queryKey: chatQueryKeys.messages(conversation.id) }),
        client.invalidateQueries({ queryKey: chatQueryKeys.conversations }),
      ]);
    },
    onError: (error) => toast.error(errorText(error, "ส่งข้อความไม่สำเร็จ กรุณาลองใหม่")),
  });

  async function loadOlder() {
    const first = messages[0];
    if (!first) return;
    setLoadingOlder(true);
    try {
      const page = await listMessages(conversation.id, { before: first.id, limit: PAGE_SIZE });
      setOlder((current) => [...page.items, ...current]);
      setHasMoreOlder(page.has_more);
    } catch (error) {
      toast.error(errorText(error, "โหลดข้อความก่อนหน้าไม่สำเร็จ"));
    } finally {
      setLoadingOlder(false);
    }
  }

  function submit() {
    const body = draft.trim();
    if (!body || send.isPending) return;
    send.mutate(body);
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit();
    }
  }

  const other = conversation.other;
  return (
    <section aria-label={`แชทกับ ${other.display_name}`} className="flex h-full min-h-0 flex-col">
      <header className="flex items-center gap-3 border-b px-4 py-3">
        <Button
          variant="ghost"
          size="icon"
          className="lg:hidden"
          onClick={onBack}
          aria-label="กลับไปรายการแชท"
        >
          <ArrowLeft aria-hidden />
        </Button>
        <Avatar name={other.display_name} className="size-9" />
        <div className="min-w-0">
          <Link
            href={`/employees/${other.id}`}
            className="block truncate font-medium hover:underline"
          >
            {other.display_name}
          </Link>
          <p className="text-muted-foreground truncate text-xs">
            {[other.job_title, other.department_name].filter(Boolean).join(" · ") || "พนักงาน"}
          </p>
        </div>
        {!other.is_active ? (
          <Badge variant="destructive" className="ml-auto">
            บัญชีถูกระงับ
          </Badge>
        ) : null}
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4" aria-live="polite">
        {latest.isPending ? (
          <div className="space-y-3" aria-busy="true">
            <Skeleton className="h-10 w-2/3" />
            <Skeleton className="ml-auto h-10 w-1/2" />
          </div>
        ) : latest.isError ? (
          <ErrorState
            message={errorText(latest.error, "โหลดข้อความไม่สำเร็จ")}
            onRetry={() => void latest.refetch()}
            retrying={latest.isFetching}
          />
        ) : messages.length === 0 ? (
          <p className="text-muted-foreground py-10 text-center text-sm">
            ยังไม่มีข้อความ เริ่มทักทาย {other.display_name} ได้เลย
          </p>
        ) : (
          <ol className="space-y-2">
            {canLoadOlder ? (
              <li className="flex justify-center pb-2">
                <Button variant="outline" size="sm" onClick={loadOlder} disabled={loadingOlder}>
                  {loadingOlder ? <Loader2 className="animate-spin" aria-hidden /> : null}
                  โหลดข้อความก่อนหน้า
                </Button>
              </li>
            ) : null}
            {messages.map((m) => {
              const mine = m.sender_id === myId;
              return (
                <li key={m.id} className={cn("flex", mine ? "justify-end" : "justify-start")}>
                  <div
                    className={cn(
                      "max-w-[80%] rounded-2xl px-3.5 py-2 text-sm break-words whitespace-pre-wrap",
                      mine ? "bg-primary text-primary-foreground" : "bg-muted",
                    )}
                  >
                    {m.body}
                    <time
                      dateTime={m.created_at}
                      title={formatDateTime(m.created_at)}
                      className={cn(
                        "mt-0.5 block text-right text-[10px]",
                        mine ? "text-primary-foreground/70" : "text-muted-foreground",
                      )}
                    >
                      {formatRelative(m.created_at)}
                    </time>
                  </div>
                </li>
              );
            })}
          </ol>
        )}
        <div ref={bottomRef} />
      </div>

      <form
        className="flex items-end gap-2 border-t p-3"
        onSubmit={(event) => {
          event.preventDefault();
          submit();
        }}
      >
        <Textarea
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={onKeyDown}
          maxLength={MESSAGE_MAX_CHARS}
          rows={1}
          disabled={!other.is_active}
          placeholder={
            other.is_active
              ? "พิมพ์ข้อความ แล้วกด Enter เพื่อส่ง"
              : "บัญชีนี้ถูกระงับ ส่งข้อความไม่ได้"
          }
          aria-label="ข้อความ"
          className="max-h-40 min-h-10 resize-none"
        />
        <Button
          type="submit"
          size="icon"
          disabled={!draft.trim() || send.isPending || !other.is_active}
          aria-label="ส่งข้อความ"
        >
          {send.isPending ? <Loader2 className="animate-spin" aria-hidden /> : <Send aria-hidden />}
        </Button>
      </form>
    </section>
  );
}

export function ChatView() {
  const { me } = useSession();
  const params = useSearchParams();
  const router = useRouter();
  const client = useQueryClient();
  const selectedId = params.get("c");
  const withUser = params.get("with");

  const conversations = useQuery({
    queryKey: chatQueryKeys.conversations,
    queryFn: ({ signal }) => listConversations(signal),
    refetchInterval: LIST_POLL_MS,
  });

  // Opened from an employee profile: find or create the thread, then show it.
  const start = useMutation({
    mutationFn: startConversation,
    onSuccess: async (conversation) => {
      await client.invalidateQueries({ queryKey: chatQueryKeys.conversations });
      router.replace(`/chat?c=${conversation.id}`);
    },
    onError: (error) => {
      toast.error(errorText(error, "เปิดแชทไม่สำเร็จ"));
      router.replace("/chat");
    },
  });
  const startRef = useRef<string | null>(null);
  useEffect(() => {
    if (withUser && startRef.current !== withUser) {
      startRef.current = withUser;
      start.mutate(withUser);
    }
  }, [withUser, start]);

  const items = conversations.data?.items ?? [];
  const selected = items.find((c) => c.id === selectedId) ?? null;

  return (
    <div className="space-y-4">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">แชท</h1>
        <p className="text-muted-foreground text-sm">
          คุยกับเพื่อนร่วมงานแบบส่วนตัว ประวัติแชทถูกเก็บไว้ในระบบ เห็นได้เฉพาะคู่สนทนาเท่านั้น
        </p>
      </div>

      <div className="bg-card grid h-[calc(100dvh-14rem)] min-h-[28rem] overflow-hidden rounded-xl border lg:grid-cols-[20rem_minmax(0,1fr)]">
        <aside
          aria-label="รายการแชท"
          className={cn(
            "min-h-0 overflow-y-auto border-r p-2",
            selectedId ? "hidden lg:block" : "block",
          )}
        >
          {conversations.isPending || start.isPending ? (
            <div className="space-y-2 p-2" aria-busy="true">
              <Skeleton className="h-14 w-full" />
              <Skeleton className="h-14 w-full" />
            </div>
          ) : conversations.isError ? (
            <ErrorState
              message={errorText(conversations.error, "โหลดรายการแชทไม่สำเร็จ")}
              onRetry={() => void conversations.refetch()}
              retrying={conversations.isFetching}
            />
          ) : items.length === 0 ? (
            <EmptyState
              icon={MessagesSquare}
              title="ยังไม่มีแชท"
              description="เปิดโปรไฟล์พนักงานในศูนย์พนักงาน แล้วกด “ส่งข้อความ”"
              action={
                <Button asChild variant="outline" size="sm">
                  <Link href="/employees">
                    <Users aria-hidden />
                    ไปที่ศูนย์พนักงาน
                  </Link>
                </Button>
              }
            />
          ) : (
            <ul className="space-y-1">
              {items.map((c) => (
                <li key={c.id}>
                  <ConversationItem
                    conversation={c}
                    active={c.id === selectedId}
                    myId={me?.user.id}
                    onSelect={() => router.push(`/chat?c=${c.id}`)}
                  />
                </li>
              ))}
            </ul>
          )}
        </aside>

        <div className={cn("min-h-0", selectedId ? "block" : "hidden lg:block")}>
          {selected ? (
            <Thread key={selected.id} conversation={selected} onBack={() => router.push("/chat")} />
          ) : (
            <div className="text-muted-foreground flex h-full items-center justify-center p-6 text-center text-sm">
              {selectedId && !conversations.isPending
                ? "ไม่พบบทสนทนานี้"
                : "เลือกแชททางซ้ายเพื่อเริ่มคุย"}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
