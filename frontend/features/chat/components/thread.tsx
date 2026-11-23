"use client";

import { useMutation, useQuery, useQueryClient, type QueryKey } from "@tanstack/react-query";
import { Check, CheckCheck, Loader2, Pencil, Send } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { toast } from "sonner";

import { ErrorState } from "@/components/common/error-state";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useSession } from "@/features/auth/hooks/use-session";
import { dayKey, formatChatDay, formatDateTime, formatRelative, formatTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import { ApiError } from "@/services/api-client";
import { chatQueryKeys, MESSAGE_MAX_CHARS } from "@/services/chat";

/**
 * One thread component for direct messages and group chats (ADR-071). Each kind supplies a
 * {@link ThreadSource} that turns its API into this common shape.
 *
 * Live updates arrive through the app-wide long poll (useChatRealtime, ADR-062); the interval
 * below is only a safety net if that connection is interrupted.
 */
const THREAD_POLL_MS = 30_000;
/** At most one "typing" signal per this interval (the server shows it for 6 s). */
const TYPING_PING_MS = 3_000;
/** "กำลังพิมพ์…" expires on the server after 6 s without a new signal. */
const TYPING_EXPIRY_MS = 6_500;
const PAGE_SIZE = 50;
/** Ids of optimistic messages that the server has not confirmed yet. */
const PENDING_PREFIX = "pending-";

export interface ThreadMessage {
  id: string;
  sender_id: string | null;
  sender_name?: string | null;
  kind: "TEXT" | "SYSTEM";
  body: string;
  created_at: string;
  edited_at: string | null;
}

export interface ThreadReader {
  name: string;
  /** Has read everything up to this time. */
  at: string;
}

export interface ThreadPage {
  items: ThreadMessage[];
  has_more: boolean;
  /** Other people's read positions (never me). */
  readers: ThreadReader[];
  /** Names of the other people typing right now. */
  typing: string[];
}

export interface ThreadSource {
  queryKey: QueryKey;
  /** Keys to refresh after a send/edit/read (the conversation lists). */
  listKeys: QueryKey[];
  fetchPage: (
    params: { before?: string; limit?: number },
    signal?: AbortSignal,
  ) => Promise<ThreadPage>;
  send: (body: string) => Promise<ThreadMessage>;
  edit: (id: string, body: string) => Promise<ThreadMessage>;
  markRead: () => Promise<unknown>;
  typing: () => Promise<unknown>;
  /** Group chats: show who wrote each message and "อ่านแล้ว N คน". */
  isGroup: boolean;
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/);
  return ((parts[0]?.[0] ?? "") + (parts[1]?.[0] ?? "")).toUpperCase();
}

export function errorText(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

/** Re-renders every `ms` so "x นาทีที่แล้ว" labels stay current between polls. */
export function useNow(ms: number): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), ms);
    return () => clearInterval(timer);
  }, [ms]);
  return now;
}

export function TypingDots({ label }: { label: string }) {
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

export function Avatar({
  name,
  className,
  group = false,
}: {
  name: string;
  className?: string;
  group?: boolean;
}) {
  return (
    <span
      aria-hidden
      className={cn(
        "flex size-10 shrink-0 items-center justify-center rounded-full text-sm font-semibold",
        group
          ? "bg-violet-500/15 text-violet-700 dark:text-violet-300"
          : "bg-primary/10 text-primary",
        className,
      )}
    >
      {initials(name)}
    </span>
  );
}

/** "สมชาย กำลังพิมพ์…", "สมชาย และ สมหญิง กำลังพิมพ์…", "3 คนกำลังพิมพ์…" */
export function typingLabel(names: string[]): string {
  if (names.length === 0) return "";
  if (names.length === 1) return `${names[0]} กำลังพิมพ์…`;
  if (names.length === 2) return `${names[0]} และ ${names[1]} กำลังพิมพ์…`;
  return `${names.length} คนกำลังพิมพ์…`;
}

export function Thread({
  source,
  header,
  canSend = true,
  disabledPlaceholder = "ส่งข้อความไม่ได้",
  emptyText,
  label,
}: {
  source: ThreadSource;
  header: ReactNode;
  canSend?: boolean;
  disabledPlaceholder?: string;
  emptyText: string;
  label: string;
}) {
  const { me } = useSession();
  const myId = me?.user.id;
  const client = useQueryClient();
  const [older, setOlder] = useState<ThreadMessage[]>([]);
  const [hasMoreOlder, setHasMoreOlder] = useState<boolean | null>(null);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [draft, setDraft] = useState("");
  // Optimistic messages: shown at once, marked "กำลังส่ง…" until the server confirms.
  const [pending, setPending] = useState<ThreadMessage[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);
  const lastPingRef = useRef(0);
  const now = useNow(30_000);
  const { queryKey, listKeys } = source;

  const refreshLists = () =>
    Promise.all(listKeys.map((key) => client.invalidateQueries({ queryKey: key })));

  const latest = useQuery({
    queryKey,
    queryFn: ({ signal }) => source.fetchPage({ limit: PAGE_SIZE }, signal),
    refetchInterval: THREAD_POLL_MS,
  });

  const messages = useMemo(() => {
    const seen = new Set<string>();
    return [...older, ...(latest.data?.items ?? []), ...pending].filter((m) =>
      seen.has(m.id) ? false : (seen.add(m.id), true),
    );
  }, [older, latest.data, pending]);
  const newestId = messages.at(-1)?.id;
  const readers = useMemo(() => latest.data?.readers ?? [], [latest.data]);
  const typingNames = useMemo(() => latest.data?.typing ?? [], [latest.data]);
  const typingKey = typingNames.join("|");
  const readKey = readers.map((r) => r.at).join("|");
  const lastMineId = [...messages]
    .reverse()
    .find((m) => m.kind === "TEXT" && m.sender_id === myId)?.id;
  const canLoadOlder = hasMoreOlder ?? latest.data?.has_more ?? false;

  // Mark as read whenever a new message shows up, then refresh the badges.
  const markRead = source.markRead;
  useEffect(() => {
    if (!newestId || newestId.startsWith(PENDING_PREFIX)) return;
    void markRead()
      .then(() =>
        Promise.all([
          client.invalidateQueries({ queryKey: chatQueryKeys.unread }),
          ...listKeys.map((key) => client.invalidateQueries({ queryKey: key })),
        ]),
      )
      .catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- run once per new message
  }, [newestId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [newestId, typingKey]);

  // No event is sent when someone simply stops typing: re-check once it would expire.
  useEffect(() => {
    if (!typingKey) return;
    const timer = setTimeout(() => void latest.refetch(), TYPING_EXPIRY_MS);
    return () => clearTimeout(timer);
  }, [typingKey, latest.data, latest]);

  // Keep the conversation list's ✓/✓✓ and "กำลังพิมพ์…" in step with the open thread.
  useEffect(() => {
    listKeys.forEach((key) => void client.invalidateQueries({ queryKey: key }));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only when reads/typing change
  }, [readKey, typingKey]);

  function onDraftChange(value: string) {
    setDraft(value);
    const at = Date.now();
    if (value.trim() && at - lastPingRef.current > TYPING_PING_MS) {
      lastPingRef.current = at;
      void source.typing().catch(() => undefined);
    }
  }

  // Sends go out one after another so quick messages keep their order.
  const queueRef = useRef<Promise<unknown>>(Promise.resolve());
  const send = useMutation({
    mutationFn: ({ body }: { body: string; tempId: string }) => {
      const run = queueRef.current.catch(() => undefined).then(() => source.send(body));
      queueRef.current = run;
      return run;
    },
    onSuccess: (saved, { tempId }) => {
      // Put the stored message in the cache before dropping the optimistic copy (no flicker).
      client.setQueryData<ThreadPage>(queryKey, (page) =>
        page && !page.items.some((m) => m.id === saved.id)
          ? { ...page, items: [...page.items, saved] }
          : page,
      );
      setPending((current) => current.filter((m) => m.id !== tempId));
      void refreshLists();
    },
    onError: (error, { body, tempId }) => {
      setPending((current) => current.filter((m) => m.id !== tempId));
      setDraft((current) => current || body);
      toast.error(errorText(error, "ส่งข้อความไม่สำเร็จ กรุณาลองใหม่"));
    },
  });

  const [editing, setEditing] = useState<{ id: string; text: string } | null>(null);
  const editMutation = useMutation({
    mutationFn: ({ id, body }: { id: string; body: string }) => source.edit(id, body),
    onSuccess: (saved) => {
      const swap = (m: ThreadMessage) => (m.id === saved.id ? saved : m);
      client.setQueryData<ThreadPage>(queryKey, (page) =>
        page ? { ...page, items: page.items.map(swap) } : page,
      );
      setOlder((current) => current.map(swap));
      setEditing(null);
      void refreshLists();
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
      const page = await source.fetchPage({ before: first.id, limit: PAGE_SIZE });
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
    if (!body || !canSend) return;
    setDraft("");
    lastPingRef.current = 0;
    const tempId = `${PENDING_PREFIX}${crypto.randomUUID()}`;
    setPending((current) => [
      ...current,
      {
        id: tempId,
        sender_id: myId ?? "",
        sender_name: me?.user.display_name ?? null,
        kind: "TEXT",
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

  function readStatus(sentAt: string): ReactNode {
    const seenBy = readers.filter((r) => new Date(r.at) >= new Date(sentAt));
    if (seenBy.length === 0) {
      return (
        <>
          <Check className="size-3.5" aria-hidden />
          ส่งแล้ว
        </>
      );
    }
    if (!source.isGroup) {
      return (
        <>
          <CheckCheck className="text-primary size-3.5" aria-hidden />
          อ่านแล้ว · {formatRelative(seenBy[0]!.at, now)}
        </>
      );
    }
    const everyone = seenBy.length === readers.length;
    return (
      <span className="flex items-center gap-1" title={seenBy.map((r) => r.name).join(", ")}>
        <CheckCheck className="text-primary size-3.5" aria-hidden />
        {everyone ? "อ่านครบทุกคนแล้ว" : `อ่านแล้ว ${seenBy.length} คน`}
      </span>
    );
  }

  return (
    <section aria-label={label} className="flex h-full min-h-0 flex-col">
      {header}

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
          <p className="text-muted-foreground py-10 text-center text-sm">{emptyText}</p>
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
              const previous = messages[index - 1];
              const newDay = !previous || dayKey(previous.created_at) !== dayKey(m.created_at);
              const separator = newDay ? (
                <div role="separator" className="flex items-center gap-3 py-1">
                  <span className="bg-border h-px flex-1" />
                  <span className="text-muted-foreground text-xs">
                    {formatChatDay(m.created_at, now)}
                  </span>
                  <span className="bg-border h-px flex-1" />
                </div>
              ) : null;

              if (m.kind === "SYSTEM") {
                return (
                  <li key={m.id} className="space-y-2">
                    {separator}
                    <p
                      className="text-muted-foreground bg-muted/60 mx-auto w-fit max-w-[90%] rounded-full px-3 py-1 text-center text-xs"
                      data-testid="system-message"
                    >
                      {m.body} · {formatTime(m.created_at)}
                    </p>
                  </li>
                );
              }

              const mine = m.sender_id === myId;
              const isPending = m.id.startsWith(PENDING_PREFIX);
              // Group chats: name above the first bubble of a run from the same person.
              const showName =
                source.isGroup &&
                !mine &&
                (newDay || previous?.kind !== "TEXT" || previous?.sender_id !== m.sender_id);
              return (
                <li key={m.id} className="space-y-2">
                  {separator}
                  <div className={cn("flex flex-col", mine ? "items-end" : "items-start")}>
                    {showName ? (
                      <span className="text-muted-foreground mb-0.5 px-1 text-xs font-medium">
                        {m.sender_name ?? "ผู้ใช้ที่ถูกลบ"}
                      </span>
                    ) : null}
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
                            isPending && "opacity-70",
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
                        {!isPending && mine && canSend ? (
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
                        {isPending ? (
                          <>
                            <Loader2 className="size-3.5 animate-spin" aria-hidden />
                            กำลังส่ง…
                          </>
                        ) : (
                          readStatus(m.created_at)
                        )}
                      </span>
                    ) : null}
                  </div>
                </li>
              );
            })}
          </ol>
        )}
        {typingNames.length ? (
          <div className="mt-2 flex items-end gap-2">
            <div className="bg-muted rounded-2xl px-3.5 py-3">
              <TypingDots label={typingLabel(typingNames).replace("…", "")} />
            </div>
            <span className="text-muted-foreground text-xs">
              {source.isGroup ? typingLabel(typingNames) : "กำลังพิมพ์…"}
            </span>
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
          disabled={!canSend}
          placeholder={canSend ? "พิมพ์ข้อความ แล้วกด Enter เพื่อส่ง" : disabledPlaceholder}
          aria-label="ข้อความ"
          className="max-h-40 min-h-10 resize-none"
        />
        <Button
          type="submit"
          size="icon"
          disabled={!draft.trim() || !canSend}
          aria-label="ส่งข้อความ"
        >
          <Send aria-hidden />
        </Button>
      </form>
    </section>
  );
}
