"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Crown, Loader2, LogOut, Pencil, UserMinus, UserPlus } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { PeoplePicker, type Picked } from "@/components/common/people-picker";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { useSession } from "@/features/auth/hooks/use-session";
import {
  addGroupMembers,
  chatQueryKeys,
  createGroup,
  getGroup,
  groupQueryKeys,
  removeGroupMember,
  renameGroup,
  type GroupDetail,
} from "@/services/chat";

import { Avatar, errorText } from "./thread";

const NAME_MAX = 100;

export function CreateGroupDialog({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (group: GroupDetail) => void;
}) {
  const { me } = useSession();
  const client = useQueryClient();
  const department = me?.user.department ?? null;
  const [name, setName] = useState("");
  const [people, setPeople] = useState<Picked[]>([]);
  const [wholeDepartment, setWholeDepartment] = useState(false);

  const create = useMutation({
    mutationFn: () =>
      createGroup({
        name: name.trim(),
        member_ids: people.map((p) => p.id),
        include_department_id: wholeDepartment && department ? department.id : null,
      }),
    onSuccess: async (group) => {
      await client.invalidateQueries({ queryKey: groupQueryKeys.list });
      toast.success(`สร้างกลุ่ม “${group.name}” แล้ว`);
      onCreated(group);
    },
    onError: (error) => toast.error(errorText(error, "สร้างกลุ่มไม่สำเร็จ")),
  });

  const ready = name.trim().length > 0 && (people.length > 0 || wholeDepartment);
  return (
    <Dialog open onOpenChange={(open) => (!open ? onClose() : undefined)}>
      <DialogContent className="max-h-[92dvh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>สร้างกลุ่มแชท</DialogTitle>
          <DialogDescription>
            คุณจะเป็นผู้ดูแลกลุ่ม เปลี่ยนชื่อ เพิ่มหรือนำสมาชิกออกได้ภายหลัง
          </DialogDescription>
        </DialogHeader>
        <form
          id="create-group"
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            if (ready && !create.isPending) create.mutate();
          }}
        >
          <div className="space-y-1.5">
            <Label htmlFor="group-name">ชื่อกลุ่ม</Label>
            <Input
              id="group-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={NAME_MAX}
              placeholder="เช่น ทีมขายภาคเหนือ"
              autoFocus
            />
          </div>
          <div className="space-y-1.5">
            <Label>สมาชิก</Label>
            <PeoplePicker
              picked={people}
              onChange={setPeople}
              placeholder="พิมพ์ชื่อเพื่อนร่วมงาน"
              label="ค้นหาสมาชิก"
              exclude={me ? [me.user.id] : []}
            />
          </div>
          {department ? (
            <label className="flex items-start gap-2 text-sm">
              <input
                type="checkbox"
                checked={wholeDepartment}
                onChange={(e) => setWholeDepartment(e.target.checked)}
                className="mt-0.5 size-4"
              />
              <span>
                เพิ่มทุกคนในแผนก {department.name}
                <span className="text-muted-foreground block text-xs">
                  เหมาะสำหรับห้องแชทประจำแผนก (คนที่เข้าแผนกภายหลังเพิ่มเองได้)
                </span>
              </span>
            </label>
          ) : null}
        </form>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            ยกเลิก
          </Button>
          <Button type="submit" form="create-group" disabled={!ready || create.isPending}>
            {create.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
            สร้างกลุ่ม
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function GroupInfoDialog({
  groupId,
  onClose,
  onLeft,
}: {
  groupId: string;
  onClose: () => void;
  onLeft: () => void;
}) {
  const { me } = useSession();
  const myId = me?.user.id;
  const client = useQueryClient();
  const detail = useQuery({
    queryKey: groupQueryKeys.detail(groupId),
    queryFn: ({ signal }) => getGroup(groupId, signal),
  });
  const [renaming, setRenaming] = useState<string | null>(null);
  const [adding, setAdding] = useState<Picked[] | null>(null);

  const refresh = () => client.invalidateQueries({ queryKey: chatQueryKeys.all });
  const onError = (fallback: string) => (error: unknown) => toast.error(errorText(error, fallback));

  const rename = useMutation({
    mutationFn: (name: string) => renameGroup(groupId, name),
    onSuccess: async () => {
      setRenaming(null);
      await refresh();
    },
    onError: onError("เปลี่ยนชื่อกลุ่มไม่สำเร็จ"),
  });
  const add = useMutation({
    mutationFn: (ids: string[]) => addGroupMembers(groupId, ids),
    onSuccess: async () => {
      setAdding(null);
      await refresh();
      toast.success("เพิ่มสมาชิกแล้ว");
    },
    onError: onError("เพิ่มสมาชิกไม่สำเร็จ"),
  });
  const remove = useMutation({
    mutationFn: (userId: string) => removeGroupMember(groupId, userId),
    onSuccess: async (_, userId) => {
      if (userId === myId) {
        toast.success("ออกจากกลุ่มแล้ว");
        onLeft();
        await client.invalidateQueries({ queryKey: groupQueryKeys.list });
        return;
      }
      await refresh();
    },
    onError: onError("ทำรายการไม่สำเร็จ"),
  });

  const group = detail.data;
  const isAdmin = group?.my_role === "ADMIN";
  const busy = rename.isPending || add.isPending || remove.isPending;

  return (
    <Dialog open onOpenChange={(open) => (!open ? onClose() : undefined)}>
      <DialogContent className="max-h-[92dvh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>ข้อมูลกลุ่ม</DialogTitle>
          <DialogDescription>
            {group ? `สมาชิก ${group.member_count} คน` : "กำลังโหลด…"}
          </DialogDescription>
        </DialogHeader>

        {detail.isPending ? (
          <Skeleton className="h-40 w-full" />
        ) : detail.isError || !group ? (
          <p className="text-destructive text-sm">
            {errorText(detail.error, "โหลดข้อมูลกลุ่มไม่สำเร็จ")}
          </p>
        ) : (
          <div className="space-y-5">
            {renaming !== null ? (
              <form
                className="flex gap-2"
                onSubmit={(event) => {
                  event.preventDefault();
                  if (renaming.trim()) rename.mutate(renaming.trim());
                }}
              >
                <Input
                  value={renaming}
                  onChange={(e) => setRenaming(e.target.value)}
                  maxLength={NAME_MAX}
                  aria-label="ชื่อกลุ่มใหม่"
                  autoFocus
                />
                <Button type="submit" disabled={!renaming.trim() || busy}>
                  บันทึก
                </Button>
                <Button type="button" variant="ghost" onClick={() => setRenaming(null)}>
                  ยกเลิก
                </Button>
              </form>
            ) : (
              <div className="flex items-center gap-3">
                <Avatar name={group.name} group />
                <p className="min-w-0 flex-1 truncate text-lg font-semibold">{group.name}</p>
                {isAdmin ? (
                  <Button variant="outline" size="sm" onClick={() => setRenaming(group.name)}>
                    <Pencil aria-hidden />
                    เปลี่ยนชื่อ
                  </Button>
                ) : null}
              </div>
            )}

            {isAdmin ? (
              adding ? (
                <div className="space-y-2 rounded-lg border p-3">
                  <PeoplePicker
                    picked={adding}
                    onChange={setAdding}
                    placeholder="พิมพ์ชื่อเพื่อเพิ่มสมาชิก"
                    label="ค้นหาสมาชิกใหม่"
                    exclude={group.members.map((m) => m.id)}
                  />
                  <div className="flex justify-end gap-2">
                    <Button variant="ghost" size="sm" onClick={() => setAdding(null)}>
                      ยกเลิก
                    </Button>
                    <Button
                      size="sm"
                      disabled={adding.length === 0 || busy}
                      onClick={() => add.mutate(adding.map((p) => p.id))}
                    >
                      {add.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
                      เพิ่ม {adding.length || ""} คน
                    </Button>
                  </div>
                </div>
              ) : (
                <Button variant="outline" size="sm" onClick={() => setAdding([])}>
                  <UserPlus aria-hidden />
                  เพิ่มสมาชิก
                </Button>
              )
            ) : null}

            <ul className="divide-y rounded-lg border" aria-label="สมาชิกในกลุ่ม">
              {group.members.map((m) => (
                <li key={m.id} className="flex items-center gap-3 px-3 py-2">
                  <Avatar name={m.display_name} className="size-8 text-xs" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">
                      {m.display_name}
                      {m.id === myId ? (
                        <span className="text-muted-foreground font-normal"> (คุณ)</span>
                      ) : null}
                    </p>
                    <p className="text-muted-foreground truncate text-xs">
                      {m.department_name ?? "—"}
                    </p>
                  </div>
                  {m.role === "ADMIN" ? (
                    <Badge variant="secondary" className="gap-1">
                      <Crown className="size-3" aria-hidden />
                      ผู้ดูแล
                    </Badge>
                  ) : null}
                  {isAdmin && m.id !== myId ? (
                    <Button
                      variant="ghost"
                      size="icon"
                      className="text-muted-foreground size-8"
                      aria-label={`นำ ${m.display_name} ออกจากกลุ่ม`}
                      title="นำออกจากกลุ่ม"
                      disabled={busy}
                      onClick={() => {
                        if (window.confirm(`นำ ${m.display_name} ออกจากกลุ่ม?`)) {
                          remove.mutate(m.id);
                        }
                      }}
                    >
                      <UserMinus className="size-4" aria-hidden />
                    </Button>
                  ) : null}
                </li>
              ))}
            </ul>
          </div>
        )}

        <DialogFooter className="sm:justify-between">
          <Button
            variant="ghost"
            className="text-destructive hover:text-destructive"
            disabled={!group || busy}
            onClick={() => {
              if (myId && window.confirm("ออกจากกลุ่มนี้? คุณจะไม่เห็นข้อความในกลุ่มอีก")) {
                remove.mutate(myId);
              }
            }}
          >
            <LogOut aria-hidden />
            ออกจากกลุ่ม
          </Button>
          <Button variant="outline" onClick={onClose}>
            ปิด
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
