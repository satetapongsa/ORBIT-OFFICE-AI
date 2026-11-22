"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Check,
  CheckCheck,
  Loader2,
  MessagesSquare,
  Pencil,
  Send,
  Users,
} from "lucide-react";
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
import { dayKey, formatChatDay, formatDateTime, formatRelative, formatTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import { ApiError } from "@/services/api-client";
import {
  canEditMessage,
  chatQueryKeys,
  editMessage,
  isSeen,
  listConversations,
  listMessages,
  markConversationRead,
  MESSAGE_MAX_CHARS,
  sendMessage,
  sendTyping,
  startConversation,
  type ChatMessage,
  type Conversation,
  type MessagePage,
} from "@/services/chat";

/**
 * Live updates arrive through the app-wide long poll (useChatRealtime, ADR-062); these
 * intervals are only a safety net if that connection is interrupted.
 */
const THREAD_POLL_MS = 30_000;
/** At most one "typing" signal per this interval (the server shows it for 6 s). */
const TYPING_PING_MS = 3_000;
const LIST_POLL_MS = 30_000;
/** "กำลังพิมพ์…" expires on the server after 6 s without a new signal. */
const TYPING_EXPIRY_MS = 6_500;
const PAGE_SIZE = 50;
/** Ids of optimistic messages that the server has not confirmed yet. */
const PENDING_PREFIX = "pending-";

function initials(name: string): string {
  const parts = name.trim().split(/\s+/);
  return ((parts[0]?.[0] ?? "") + (parts[1]?.[0] ?? "")).toUpperCase();
}

function errorText(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

/** Re-renders every `ms` so "x นาทีที่แล้ว" labels stay current between polls. */
function useNow(ms: number): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), ms);
    return () => clearInterval(timer);
  }, [ms]);
  return now;
}

function TypingDots({ label }: { label: string }) {
  return (
    <span className="inline-flex items-center gap-1" role="status" aria-label={label}>
      {[0, 150, 300].map((delay) => (
        <span
          key={delay}
          aria-hidden
          className="bg-muted-foreground/70 size-1.5 animate-bounce rounded-full"
          style={{ animationDelay: `${delay}ms` }}
        />
      ))}
    </span>
  );
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
  const mineLast = last !== null && last.sender_id === myId;
  const preview = last ? `${mineLast ? "คุณ: " : ""}${last.body}` : "ยังไม่มีข้อความ";
  const seen = mineLast && isSeen(conversation.other_last_read_at, last.created_at);
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
          {conversation.other_typing ? (
            <span className="text-primary truncate text-xs italic">กำลังพิมพ์…</span>
          ) : (
            <span
              className={cn(
                "flex min-w-0 items-center gap-1 text-xs",
                conversation.unread_count ? "text-foreground font-medium" : "text-muted-foreground",
              )}
            >
              {mineLast ? (
                seen ? (
                  <CheckCheck className="text-primary size-3.5 shrink-0" aria-label="อ่านแล้ว" />
                ) : (
                  <Check className="size-3.5 shrink-0" aria-label="ส่งแล้ว" />
                )
              ) : null}
              <span className="truncate">{preview}</span>
            </span>
          )}
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
  // Optimistic messages: shown at once, marked "กำลังส่ง…" until the server confirms.
  const [pending, setPending] = useState<ChatMessage[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);
  const lastPingRef = useRef(0);
  const now = useNow(30_000);

  const latest = useQuery({
    queryKey: chatQueryKeys.messages(conversation.id),
    queryFn: ({ signal }) => listMessages(conversation.id, { limit: PAGE_SIZE }, signal),
    refetchInterval: THREAD_POLL_MS,
  });

  const messages = useMemo(() => {
    const seen = new Set<string>();
    return [...older, ...(latest.data?.items ?? []), ...pending].filter((m) =>
      seen.has(m.id) ? false : (seen.add(m.id), true),
    );
  }, [older, latest.data, pending]);
  const newestId = messages.at(-1)?.id;
  const otherReadAt = latest.data?.other_last_read_at ?? null;
  const otherTyping = latest.data?.other_typing ?? false;
  const lastMineId = [...messages].reverse().find((m) => m.sender_id === myId)?.id;
  const canLoadOlder = hasMoreOlder ?? latest.data?.has_more ?? false;

  // Mark as read whenever a new message shows up, then refresh the badges.
  useEffect(() => {
    if (!newestId || newestId.startsWith(PENDING_PREFIX)) return;
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
  }, [newestId, otherTyping]);

  // No event is sent when the other person simply stops typing: re-check once it would expire.
  useEffect(() => {
    if (!otherTyping) return;
    const timer = setTimeout(() => void latest.refetch(), TYPING_EXPIRY_MS);
    return () => clearTimeout(timer);
  }, [otherTyping, latest.data, latest]);

  // Keep the conversation list's ✓/✓✓ and "กำลังพิมพ์…" in step with the open thread.
  useEffect(() => {
    void client.invalidateQueries({ queryKey: chatQueryKeys.conversations });
  }, [otherReadAt, otherTyping, client]);

  function onDraftChange(value: string) {
    setDraft(value);
    const at = Date.now();
    if (value.trim() && at - lastPingRef.current > TYPING_PING_MS) {
      lastPingRef.current = at;
      void sendTyping(conversation.id).catch(() => undefined);
    }
  }

  // Sends go out one after another so quick messages keep their order.
  const queueRef = useRef<Promise<unknown>>(Promise.resolve());
  const messagesKey = chatQueryKeys.messages(conversation.id);
  const send = useMutation({
    mutationFn: ({ body }: { body: string; tempId: string }) => {
      const run = queueRef.current
        .catch(() => undefined)
        .then(() => sendMessage(conversation.id, body));
      queueRef.current = run;
      return run;
    },
    onSuccess: (saved, { tempId }) => {
      // Put the stored message in the cache before dropping the optimistic copy (no flicker).
      client.setQueryData<MessagePage>(messagesKey, (page) =>
        page && !page.items.some((m) => m.id === saved.id)
          ? { ...page, items: [...page.items, saved] }
          : page,
      );
      setPending((current) => current.filter((m) => m.id !== tempId));
      void client.invalidateQueries({ queryKey: chatQueryKeys.conversations });
    },
    onError: (error, { body, tempId }) => {
      setPending((current) => current.filter((m) => m.id !== tempId));
      setDraft((current) => current || body);
      toast.error(errorText(error, "ส่งข้อความไม่สำเร็จ กรุณาลองใหม่"));
    },
  });

  const [editing, setEditing] = useState<{ id: string; text: string } | null>(null);
  const editMutation = useMutation({
    mutationFn: ({ id, body }: { id: string; body: string }) =>
      editMessage(conversation.id, id, body),
    onSuccess: (saved) => {
      const swap = (m: ChatMessage) => (m.id === saved.id ? saved : m);
      client.setQueryData<MessagePage>(messagesKey, (page) =>
        page ? { ...page, items: page.items.map(swap) } : page,
      );
      setOlder((current) => current.map(swap));
      setEditing(null);
      void client.invalidateQueries({ queryKey: chatQueryKeys.conversations });
    },
    onError: (error) => toast.error(errorText(error, "แก้ไขข้อความไม่สำเร็จ")),
  });

  function saveEdit() {
    const body = editing?.text.trim();
    if (!editing || !body || editMutation.isPending) return;
    editMutation.mutate({ id: editing.id, body });
  }

  function onEditKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      setEditing(null);
    } else if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      saveEdit();
    }
  }

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
    if (!body) return;
    setDraft("");
    lastPingRef.current = 0;
    const tempId = `${PENDING_PREFIX}${crypto.randomUUID()}`;
    setPending((current) => [
      ...current,
      {
        id: tempId,
        conversation_id: conversation.id,
        sender_id: myId ?? "",
        body,
        created_at: new Date().toISOString(),
        edited_at: null,
      },
    ]);
    send.mutate({ body, tempId });
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
            {messages.map((m, index) => {
              const mine = m.sender_id === myId;
              const previous = messages[index - 1];
              const newDay = !previous || dayKey(previous.created_at) !== dayKey(m.created_at);
              const pending = m.id.startsWith(PENDING_PREFIX);
              const seen = !pending && isSeen(otherReadAt, m.created_at);
              return (
                <li key={m.id} className="space-y-2">
                  {newDay ? (
                    <div role="separator" className="flex items-center gap-3 py-1">
                      <span className="bg-border h-px flex-1" />
                      <span className="text-muted-foreground text-xs">
                        {formatChatDay(m.created_at, now)}
                      </span>
                      <span className="bg-border h-px flex-1" />
                    </div>
                  ) : null}
                  <div className={cn("flex flex-col", mine ? "items-end" : "items-start")}>
                    {editing?.id === m.id ? (
                      <div
                        className="w-full max-w-[80%] space-y-2"
                        // Keep the whole editor (with its buttons) on screen.
                        ref={(node) => node?.scrollIntoView({ block: "nearest" })}
                      >
                        <Textarea
                          autoFocus
                          value={editing.text}
                          onChange={(event) => setEditing({ id: m.id, text: event.target.value })}
                          onKeyDown={onEditKeyDown}
                          maxLength={MESSAGE_MAX_CHARS}
                          aria-label="แก้ไขข้อความ"
                          className="min-h-16 resize-none"
                        />
                        <div className="flex items-center justify-end gap-2">
                          <span className="text-muted-foreground mr-auto text-[11px]">
                            Enter เพื่อบันทึก · Esc เพื่อยกเลิก
                          </span>
                          <Button size="sm" variant="ghost" onClick={() => setEditing(null)}>
                            ยกเลิก
                          </Button>
                          <Button
                            size="sm"
                            onClick={saveEdit}
                            disabled={!editing.text.trim() || editMutation.isPending}
                          >
                            {editMutation.isPending ? (
                              <Loader2 className="animate-spin" aria-hidden />
                            ) : null}
                            บันทึก
                          </Button>
                        </div>
                      </div>
                    ) : (
                      <div
                        className={cn(
                          // Full width row, so the bubble's 80% limit is measured against the
                          // thread (a shrink-to-fit row squeezed short messages to one letter).
                          "group flex w-full items-center gap-1",
                          mine && "flex-row-reverse",
                        )}
                      >
                        <div
                          className={cn(
                            "max-w-[80%] min-w-0 rounded-2xl px-3.5 py-2 text-sm leading-relaxed [overflow-wrap:anywhere] whitespace-pre-wrap",
                            mine ? "bg-primary text-primary-foreground" : "bg-muted",
                            pending && "opacity-70",
                          )}
                        >
                          {m.body}
                          <time
                            dateTime={m.created_at}
                            title={formatDateTime(m.created_at)}
                            className={cn(
                              "mt-0.5 block text-right text-[10px] whitespace-nowrap",
                              mine ? "text-primary-foreground/70" : "text-muted-foreground",
                            )}
                          >
                            {m.edited_at ? "แก้ไขแล้ว · " : ""}
                            {formatTime(m.created_at)}
                          </time>
                        </div>
                        {!pending && canEditMessage(m, myId) ? (
                          <Button
                            variant="ghost"
                            size="icon"
                            className="text-muted-foreground size-7 shrink-0 opacity-60 group-hover:opacity-100 focus-visible:opacity-100 sm:opacity-0"
                            onClick={() => setEditing({ id: m.id, text: m.body })}
                            aria-label="แก้ไขข้อความ"
                            title="แก้ไขข้อความ"
                          >
                            <Pencil className="size-3.5" aria-hidden />
                          </Button>
                        ) : null}
                      </div>
                    )}
                    {m.id === lastMineId ? (
                      <span
                        className="text-muted-foreground mt-0.5 flex items-center gap-1 text-[11px]"
                        data-testid="message-status"
                      >
                        {pending ? (
                          <>
                            <Loader2 className="size-3.5 animate-spin" aria-hidden />
                            กำลังส่ง…
                          </>
                        ) : seen && otherReadAt ? (
                          <>
                            <CheckCheck className="text-primary size-3.5" aria-hidden />
                            อ่านแล้ว · {formatRelative(otherReadAt, now)}
                          </>
                        ) : (
                          <>
                            <Check className="size-3.5" aria-hidden />
                            ส่งแล้ว
                          </>
                        )}
                      </span>
                    ) : null}
                  </div>
                </li>
              );
            })}
          </ol>
        )}
        {otherTyping ? (
          <div className="mt-2 flex items-end gap-2">
            <div className="bg-muted rounded-2xl px-3.5 py-3">
              <TypingDots label={`${other.display_name} กำลังพิมพ์`} />
            </div>
            <span className="text-muted-foreground text-xs">กำลังพิมพ์…</span>
          </div>
        ) : null}
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
          onChange={(event) => onDraftChange(event.target.value)}
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
          disabled={!draft.trim() || !other.is_active}
          aria-label="ส่งข้อความ"
        >
          <Send aria-hidden />
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
