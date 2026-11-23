"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Check, CheckCheck, Info, MessagesSquare, Plus, Users } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { EmptyState } from "@/components/common/empty-state";
import { ErrorState } from "@/components/common/error-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useSession } from "@/features/auth/hooks/use-session";
import { formatRelative } from "@/lib/format";
import { cn } from "@/lib/utils";
import {
  chatQueryKeys,
  editGroupMessage,
  editMessage,
  groupQueryKeys,
  isSeen,
  listConversations,
  listGroupMessages,
  listGroups,
  listMessages,
  markConversationRead,
  markGroupRead,
  sendGroupMessage,
  sendGroupTyping,
  sendMessage,
  sendTyping,
  startConversation,
  type ChatMessage,
  type Conversation,
  type GroupMessage,
  type GroupSummary,
} from "@/services/chat";

import { CreateGroupDialog, GroupInfoDialog } from "./group-dialogs";
import {
  Avatar,
  errorText,
  Thread,
  typingLabel,
  type ThreadMessage,
  type ThreadSource,
} from "./thread";

const LIST_POLL_MS = 30_000;

const fromDm = (m: ChatMessage): ThreadMessage => ({ ...m, kind: "TEXT", sender_name: null });
const fromGroup = (m: GroupMessage): ThreadMessage => m;

type ListEntry =
  | { kind: "dm"; at: string | null; item: Conversation }
  | { kind: "group"; at: string | null; item: GroupSummary };

function UnreadBadge({ count }: { count: number }) {
  if (!count) return null;
  return (
    <Badge className="h-5 min-w-5 shrink-0 justify-center px-1.5 text-[11px]">
      {count > 99 ? "99+" : count}
    </Badge>
  );
}

function ListRow({
  active,
  onSelect,
  avatar,
  title,
  at,
  unread,
  children,
}: {
  active: boolean;
  onSelect: () => void;
  avatar: React.ReactNode;
  title: React.ReactNode;
  at: string | null;
  unread: number;
  children: React.ReactNode;
}) {
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
      {avatar}
      <span className="min-w-0 flex-1">
        <span className="flex items-baseline justify-between gap-2">
          <span className="truncate text-sm font-medium">{title}</span>
          {at ? (
            <span className="text-muted-foreground shrink-0 text-xs">{formatRelative(at)}</span>
          ) : null}
        </span>
        <span className="flex items-center justify-between gap-2">
          {children}
          <UnreadBadge count={unread} />
        </span>
      </span>
    </button>
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
    <ListRow
      active={active}
      onSelect={onSelect}
      avatar={<Avatar name={conversation.other.display_name} />}
      title={conversation.other.display_name}
      at={conversation.last_message_at}
      unread={conversation.unread_count}
    >
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
    </ListRow>
  );
}

function GroupItem({
  group,
  active,
  myId,
  onSelect,
}: {
  group: GroupSummary;
  active: boolean;
  myId: string | undefined;
  onSelect: () => void;
}) {
  const last = group.last_message;
  const who =
    last && last.kind === "TEXT"
      ? last.sender_id === myId
        ? "คุณ: "
        : `${last.sender_name ?? "ผู้ใช้"}: `
      : "";
  const preview = last ? `${who}${last.body}` : "ยังไม่มีข้อความ";
  return (
    <ListRow
      active={active}
      onSelect={onSelect}
      avatar={<Avatar name={group.name} group />}
      title={
        <span className="flex items-center gap-1">
          <Users className="text-muted-foreground size-3.5 shrink-0" aria-label="กลุ่ม" />
          <span className="truncate">{group.name}</span>
          <span className="text-muted-foreground shrink-0 text-xs font-normal">
            ({group.member_count})
          </span>
        </span>
      }
      at={group.last_message_at}
      unread={group.unread_count}
    >
      {group.typing_names.length ? (
        <span className="text-primary truncate text-xs italic">
          {typingLabel(group.typing_names)}
        </span>
      ) : (
        <span
          className={cn(
            "min-w-0 truncate text-xs",
            group.unread_count ? "text-foreground font-medium" : "text-muted-foreground",
          )}
        >
          {preview}
        </span>
      )}
    </ListRow>
  );
}

function BackButton({ onBack }: { onBack: () => void }) {
  return (
    <Button
      variant="ghost"
      size="icon"
      className="lg:hidden"
      onClick={onBack}
      aria-label="กลับไปรายการแชท"
    >
      <ArrowLeft aria-hidden />
    </Button>
  );
}

function DmThread({ conversation, onBack }: { conversation: Conversation; onBack: () => void }) {
  const other = conversation.other;
  const id = conversation.id;
  const source = useMemo<ThreadSource>(
    () => ({
      queryKey: chatQueryKeys.messages(id),
      listKeys: [chatQueryKeys.conversations],
      isGroup: false,
      fetchPage: async (params, signal) => {
        const page = await listMessages(id, params, signal);
        return {
          items: page.items.map(fromDm),
          has_more: page.has_more,
          readers: page.other_last_read_at
            ? [{ name: other.display_name, at: page.other_last_read_at }]
            : [],
          typing: page.other_typing ? [other.display_name] : [],
        };
      },
      send: async (body) => fromDm(await sendMessage(id, body)),
      edit: async (mid, body) => fromDm(await editMessage(id, mid, body)),
      markRead: () => markConversationRead(id),
      typing: () => sendTyping(id),
    }),
    [id, other.display_name],
  );
  return (
    <Thread
      source={source}
      label={`แชทกับ ${other.display_name}`}
      emptyText={`ยังไม่มีข้อความ เริ่มทักทาย ${other.display_name} ได้เลย`}
      canSend={other.is_active}
      disabledPlaceholder="บัญชีนี้ถูกระงับ ส่งข้อความไม่ได้"
      header={
        <header className="flex items-center gap-3 border-b px-4 py-3">
          <BackButton onBack={onBack} />
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
      }
    />
  );
}

function GroupThread({
  group,
  onBack,
  onLeft,
}: {
  group: GroupSummary;
  onBack: () => void;
  onLeft: () => void;
}) {
  const { me } = useSession();
  const myId = me?.user.id;
  const id = group.id;
  const [info, setInfo] = useState(false);
  const source = useMemo<ThreadSource>(
    () => ({
      queryKey: groupQueryKeys.messages(id),
      listKeys: [groupQueryKeys.list],
      isGroup: true,
      fetchPage: async (params, signal) => {
        const page = await listGroupMessages(id, params, signal);
        return {
          items: page.items.map(fromGroup),
          has_more: page.has_more,
          readers: page.reads
            .filter((r) => r.id !== myId)
            .map((r) => ({ name: r.display_name, at: r.last_read_at ?? "1970-01-01T00:00:00Z" })),
          typing: page.typing_names,
        };
      },
      send: async (body) => fromGroup(await sendGroupMessage(id, body)),
      edit: async (mid, body) => fromGroup(await editGroupMessage(id, mid, body)),
      markRead: () => markGroupRead(id),
      typing: () => sendGroupTyping(id),
    }),
    [id, myId],
  );
  return (
    <>
      <Thread
        source={source}
        label={`กลุ่ม ${group.name}`}
        emptyText="ยังไม่มีข้อความในกลุ่มนี้"
        header={
          <header className="flex items-center gap-3 border-b px-4 py-3">
            <BackButton onBack={onBack} />
            <Avatar name={group.name} group className="size-9" />
            <button
              type="button"
              className="min-w-0 text-left"
              onClick={() => setInfo(true)}
              aria-label="ดูสมาชิกในกลุ่ม"
            >
              <span className="block truncate font-medium hover:underline">{group.name}</span>
              <span className="text-muted-foreground block truncate text-xs">
                สมาชิก {group.member_count} คน{group.my_role === "ADMIN" ? " · คุณเป็นผู้ดูแล" : ""}
              </span>
            </button>
            <Button
              variant="ghost"
              size="icon"
              className="ml-auto"
              onClick={() => setInfo(true)}
              aria-label="ข้อมูลกลุ่ม"
              title="ข้อมูลกลุ่ม"
            >
              <Info aria-hidden />
            </Button>
          </header>
        }
      />
      {info ? (
        <GroupInfoDialog groupId={id} onClose={() => setInfo(false)} onLeft={onLeft} />
      ) : null}
    </>
  );
}

export function ChatView() {
  const { me } = useSession();
  const myId = me?.user.id;
  const params = useSearchParams();
  const router = useRouter();
  const client = useQueryClient();
  const selectedDm = params.get("c");
  const selectedGroup = params.get("g");
  const withUser = params.get("with");
  const hasSelection = Boolean(selectedDm || selectedGroup);
  const [creating, setCreating] = useState(false);

  const conversations = useQuery({
    queryKey: chatQueryKeys.conversations,
    queryFn: ({ signal }) => listConversations(signal),
    refetchInterval: LIST_POLL_MS,
  });
  const groups = useQuery({
    queryKey: groupQueryKeys.list,
    queryFn: ({ signal }) => listGroups(signal),
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

  const dms = useMemo(() => conversations.data?.items ?? [], [conversations.data]);
  const groupItems = useMemo(() => groups.data ?? [], [groups.data]);
  // Direct messages and groups in one list, most recent activity first.
  const entries = useMemo<ListEntry[]>(() => {
    const all: ListEntry[] = [
      ...dms.map((item) => ({ kind: "dm" as const, at: item.last_message_at, item })),
      ...groupItems.map((item) => ({ kind: "group" as const, at: item.last_message_at, item })),
    ];
    return all.sort((a, b) => (b.at ?? "").localeCompare(a.at ?? ""));
  }, [dms, groupItems]);
  const selectedConversation = dms.find((c) => c.id === selectedDm) ?? null;
  const selectedGroupItem = groupItems.find((g) => g.id === selectedGroup) ?? null;
  const loading = conversations.isPending || groups.isPending || start.isPending;
  const failed = conversations.isError ? conversations : groups.isError ? groups : null;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">แชท</h1>
          <p className="text-muted-foreground text-sm">
            คุยกับเพื่อนร่วมงานแบบส่วนตัวหรือเป็นกลุ่ม ข้อความเห็นได้เฉพาะคนในแชทเท่านั้น
          </p>
        </div>
        <Button onClick={() => setCreating(true)}>
          <Plus aria-hidden />
          สร้างกลุ่ม
        </Button>
      </div>

      <div className="bg-card grid h-[calc(100dvh-14rem)] min-h-[28rem] overflow-hidden rounded-xl border lg:grid-cols-[20rem_minmax(0,1fr)]">
        <aside
          aria-label="รายการแชท"
          className={cn(
            "min-h-0 overflow-y-auto border-r p-2",
            hasSelection ? "hidden lg:block" : "block",
          )}
        >
          {loading ? (
            <div className="space-y-2 p-2" aria-busy="true">
              <Skeleton className="h-14 w-full" />
              <Skeleton className="h-14 w-full" />
            </div>
          ) : failed ? (
            <ErrorState
              message={errorText(failed.error, "โหลดรายการแชทไม่สำเร็จ")}
              onRetry={() => void failed.refetch()}
              retrying={failed.isFetching}
            />
          ) : entries.length === 0 ? (
            <EmptyState
              icon={MessagesSquare}
              title="ยังไม่มีแชท"
              description="เปิดโปรไฟล์พนักงานในศูนย์พนักงาน แล้วกด “ส่งข้อความ” หรือสร้างกลุ่มแชท"
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
              {entries.map((entry) =>
                entry.kind === "dm" ? (
                  <li key={`c-${entry.item.id}`}>
                    <ConversationItem
                      conversation={entry.item}
                      active={entry.item.id === selectedDm}
                      myId={myId}
                      onSelect={() => router.push(`/chat?c=${entry.item.id}`)}
                    />
                  </li>
                ) : (
                  <li key={`g-${entry.item.id}`}>
                    <GroupItem
                      group={entry.item}
                      active={entry.item.id === selectedGroup}
                      myId={myId}
                      onSelect={() => router.push(`/chat?g=${entry.item.id}`)}
                    />
                  </li>
                ),
              )}
            </ul>
          )}
        </aside>

        <div className={cn("min-h-0", hasSelection ? "block" : "hidden lg:block")}>
          {selectedConversation ? (
            <DmThread
              key={selectedConversation.id}
              conversation={selectedConversation}
              onBack={() => router.push("/chat")}
            />
          ) : selectedGroupItem ? (
            <GroupThread
              key={selectedGroupItem.id}
              group={selectedGroupItem}
              onBack={() => router.push("/chat")}
              onLeft={() => router.push("/chat")}
            />
          ) : (
            <div className="text-muted-foreground flex h-full items-center justify-center p-6 text-center text-sm">
              {hasSelection && !loading ? "ไม่พบบทสนทนานี้" : "เลือกแชททางซ้ายเพื่อเริ่มคุย"}
            </div>
          )}
        </div>
      </div>

      {creating ? (
        <CreateGroupDialog
          onClose={() => setCreating(false)}
          onCreated={(group) => {
            setCreating(false);
            router.push(`/chat?g=${group.id}`);
          }}
        />
      ) : null}
    </div>
  );
}
