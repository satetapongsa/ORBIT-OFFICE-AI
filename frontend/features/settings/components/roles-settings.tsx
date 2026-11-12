"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Lock, Plus, Save, ShieldCheck, Trash2 } from "lucide-react";
import { useId, useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { ErrorState } from "@/components/common/error-state";
import { FormField } from "@/components/common/form-field";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { roleLabel } from "@/features/auth/labels";
import { useSession } from "@/features/auth/hooks/use-session";
import { ApiErrorAlert } from "@/features/employees/components/account-dialogs";
import { cn } from "@/lib/utils";
import { ApiError } from "@/services/api-client";
import {
  createRole,
  deleteRole,
  listPermissions,
  listRoleDetails,
  roleQueryKeys,
  setRolePermissions,
  updateRole,
  type Permission,
  type RoleDetail,
} from "@/services/roles";

/** Permission domains (the part before ":") in display order. */
export const PERMISSION_GROUPS: { domain: string; label: string }[] = [
  { domain: "users", label: "ผู้ใช้" },
  { domain: "departments", label: "แผนก" },
  { domain: "roles", label: "บทบาทและสิทธิ์" },
  { domain: "employees", label: "ข้อมูลพนักงาน" },
  { domain: "documents", label: "เอกสาร" },
  { domain: "tasks", label: "งาน" },
  { domain: "tickets", label: "แจ้งปัญหาไอที" },
  { domain: "analytics", label: "รายงานและการวิเคราะห์" },
  { domain: "reports", label: "ส่งออกรายงาน" },
  { domain: "ai", label: "ผู้ช่วย AI" },
  { domain: "audit", label: "บันทึกการใช้งาน" },
  { domain: "system", label: "ระบบ" },
];

export function groupPermissions(permissions: Permission[]) {
  const known = new Set(PERMISSION_GROUPS.map((g) => g.domain));
  const groups = PERMISSION_GROUPS.map((g) => ({
    ...g,
    items: permissions.filter((p) => p.code.split(":")[0] === g.domain),
  }));
  const other = permissions.filter((p) => !known.has(p.code.split(":")[0] ?? ""));
  if (other.length > 0) groups.push({ domain: "other", label: "อื่นๆ", items: other });
  return groups.filter((g) => g.items.length > 0);
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

function useInvalidateRoles() {
  const client = useQueryClient();
  return () => client.invalidateQueries({ queryKey: roleQueryKeys.all });
}

const roleFormSchema = z.object({
  code: z
    .string()
    .trim()
    .regex(/^[A-Z][A-Z0-9_]{1,49}$/, "ใช้ตัวพิมพ์ใหญ่ ตัวเลข หรือ _ ขึ้นต้นด้วยตัวอักษร 2–50 ตัว"),
  name: z.string().trim().min(1, "กรุณาระบุชื่อบทบาท").max(100, "ชื่อยาวเกิน 100 ตัวอักษร"),
  description: z.string().trim().max(500, "คำอธิบายยาวเกิน 500 ตัวอักษร"),
});
type RoleFormValues = z.infer<typeof roleFormSchema>;

function CreateRoleDialog({ onCreated }: { onCreated: (role: RoleDetail) => void }) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const invalidate = useInvalidateRoles();
  const create = useMutation({
    mutationFn: (v: RoleFormValues) => createRole({ ...v, permissions: [] }),
    onSuccess: () => invalidate(),
  });
  const form = useForm<RoleFormValues>({
    resolver: zodResolver(roleFormSchema),
    defaultValues: { code: "", name: "", description: "" },
  });
  const close = () => {
    setOpen(false);
    form.reset();
    create.reset();
  };
  const onSubmit = form.handleSubmit((v) =>
    create.mutate(v, {
      onSuccess: (role) => {
        toast.success(`สร้างบทบาท ${role.name} แล้ว เลือกสิทธิ์ให้บทบาทนี้ต่อได้เลย`);
        close();
        onCreated(role);
      },
    }),
  );
  return (
    <Dialog open={open} onOpenChange={(next) => (next ? setOpen(true) : close())}>
      <DialogTrigger asChild>
        <Button size="sm">
          <Plus aria-hidden />
          สร้างบทบาท
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>สร้างบทบาทใหม่</DialogTitle>
          <DialogDescription>
            บทบาทใหม่ยังไม่มีสิทธิ์ใด ๆ จนกว่าคุณจะเลือกและบันทึก
          </DialogDescription>
        </DialogHeader>
        <form noValidate onSubmit={onSubmit} className="space-y-4" aria-label="ฟอร์มสร้างบทบาท">
          <ApiErrorAlert error={create.error} />
          <FormField
            label="รหัสบทบาท"
            placeholder="เช่น FINANCE_LEAD"
            hint="ใช้อ้างอิงในระบบ เปลี่ยนภายหลังไม่ได้"
            registration={form.register("code")}
            error={form.formState.errors.code}
          />
          <FormField
            label="ชื่อบทบาท"
            registration={form.register("name")}
            error={form.formState.errors.name}
          />
          <div className="space-y-1.5">
            <Label htmlFor={id}>คำอธิบาย</Label>
            <Textarea id={id} rows={2} {...form.register("description")} />
          </div>
          <DialogFooter>
            <Button type="submit" disabled={create.isPending}>
              {create.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
              สร้าง
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function DeleteRoleDialog({ role, onDeleted }: { role: RoleDetail; onDeleted: () => void }) {
  const [open, setOpen] = useState(false);
  const invalidate = useInvalidateRoles();
  const remove = useMutation({ mutationFn: () => deleteRole(role.id) });
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) remove.reset();
      }}
    >
      <DialogTrigger asChild>
        <Button size="sm" variant="outline" className="text-destructive">
          <Trash2 aria-hidden />
          ลบบทบาท
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>ลบบทบาท “{role.name}”?</DialogTitle>
          <DialogDescription>
            ลบได้เฉพาะบทบาทที่ไม่มีผู้ใช้ถืออยู่ การลบย้อนกลับไม่ได้ (บันทึกไว้ในบันทึกการใช้งาน)
          </DialogDescription>
        </DialogHeader>
        <ApiErrorAlert error={remove.error} />
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="outline">ยกเลิก</Button>
          </DialogClose>
          <Button
            variant="destructive"
            disabled={remove.isPending}
            onClick={() =>
              remove.mutate(undefined, {
                onSuccess: async () => {
                  toast.success("ลบบทบาทแล้ว");
                  setOpen(false);
                  onDeleted();
                  await invalidate();
                },
              })
            }
          >
            {remove.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
            ลบบทบาท
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function RoleDetailsForm({ role, canManage }: { role: RoleDetail; canManage: boolean }) {
  const ids = { name: useId(), description: useId() };
  const invalidate = useInvalidateRoles();
  const [name, setName] = useState(role.name);
  const [description, setDescription] = useState(role.description);
  const save = useMutation({
    mutationFn: () => updateRole(role.id, { name: name.trim(), description: description.trim() }),
    onSuccess: async () => {
      toast.success("บันทึกข้อมูลบทบาทแล้ว");
      await invalidate();
    },
    onError: (e) => toast.error(errorMessage(e, "บันทึกไม่สำเร็จ")),
  });
  if (!canManage) {
    return role.description ? (
      <p className="text-muted-foreground text-sm">{role.description}</p>
    ) : null;
  }
  const dirty = name.trim() !== role.name || description.trim() !== role.description;
  return (
    <form
      className="grid gap-3 sm:grid-cols-[minmax(0,14rem)_minmax(0,1fr)_auto] sm:items-end"
      onSubmit={(e) => {
        e.preventDefault();
        if (name.trim()) save.mutate();
      }}
    >
      <div className="space-y-1.5">
        <Label htmlFor={ids.name}>ชื่อบทบาท</Label>
        <Input
          id={ids.name}
          value={name}
          maxLength={100}
          onChange={(e) => setName(e.target.value)}
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor={ids.description}>คำอธิบาย</Label>
        <Input
          id={ids.description}
          value={description}
          maxLength={500}
          onChange={(e) => setDescription(e.target.value)}
        />
      </div>
      <Button type="submit" variant="outline" disabled={!dirty || !name.trim() || save.isPending}>
        {save.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
        บันทึกชื่อ
      </Button>
    </form>
  );
}

function PermissionEditor({
  role,
  permissions,
  canManage,
}: {
  role: RoleDetail;
  permissions: Permission[];
  canManage: boolean;
}) {
  const { has } = useSession();
  const invalidate = useInvalidateRoles();
  const [selected, setSelected] = useState<Set<string>>(() => new Set(role.permissions));
  const save = useMutation({
    mutationFn: () => setRolePermissions(role.id, [...selected].sort()),
    onSuccess: async () => {
      toast.success(`บันทึกสิทธิ์ของ ${roleLabel(role.code, role.name)} แล้ว มีผลทันที`);
      await invalidate();
    },
  });
  const editable = canManage && !role.is_locked;
  const groups = useMemo(() => groupPermissions(permissions), [permissions]);
  const original = new Set(role.permissions);
  const changed =
    selected.size !== original.size || [...selected].some((code) => !original.has(code));

  return (
    <div className="space-y-4">
      {role.is_locked ? (
        <p className="text-muted-foreground flex items-center gap-1.5 text-sm">
          <Lock className="size-4" aria-hidden />
          บทบาทนี้มีสิทธิ์ทั้งหมดของระบบเสมอ แก้ไขไม่ได้
        </p>
      ) : editable ? (
        <p className="text-muted-foreground text-xs">
          ให้หรือถอนได้เฉพาะสิทธิ์ที่คุณเองมี (ช่องที่เป็นสีจางคือสิทธิ์ที่คุณไม่มี)
        </p>
      ) : null}
      <ApiErrorAlert error={save.error} />
      <div className="grid gap-4 md:grid-cols-2">
        {groups.map((group) => (
          <fieldset key={group.domain} className="space-y-2 rounded-lg border p-3">
            <legend className="px-1 text-sm font-medium">{group.label}</legend>
            {group.items.map((p) => {
              const grantable = editable && has(p.code);
              return (
                <label
                  key={p.code}
                  className={cn(
                    "flex items-start gap-2 text-sm",
                    !grantable && editable && "opacity-60",
                  )}
                >
                  <input
                    type="checkbox"
                    className="mt-0.5 size-4"
                    checked={role.is_locked || selected.has(p.code)}
                    disabled={!grantable || save.isPending}
                    onChange={(e) =>
                      setSelected((current) => {
                        const next = new Set(current);
                        if (e.target.checked) next.add(p.code);
                        else next.delete(p.code);
                        return next;
                      })
                    }
                  />
                  <span>
                    {p.description}
                    <span className="text-muted-foreground block font-mono text-xs">{p.code}</span>
                  </span>
                </label>
              );
            })}
          </fieldset>
        ))}
      </div>
      {editable ? (
        <div className="flex flex-wrap items-center gap-2">
          <Button disabled={!changed || save.isPending} onClick={() => save.mutate()}>
            {save.isPending ? (
              <Loader2 className="animate-spin" aria-hidden />
            ) : (
              <Save aria-hidden />
            )}
            บันทึกสิทธิ์
          </Button>
          {changed ? (
            <Button
              variant="ghost"
              disabled={save.isPending}
              onClick={() => {
                setSelected(new Set(role.permissions));
                save.reset();
              }}
            >
              ยกเลิกการเปลี่ยนแปลง
            </Button>
          ) : null}
          <span className="text-muted-foreground text-xs">
            เลือกไว้ {selected.size} จาก {permissions.length} สิทธิ์
          </span>
        </div>
      ) : null}
    </div>
  );
}

export function RolesSettings() {
  const { has } = useSession();
  const canManage = has("roles:manage");
  const roles = useQuery({
    queryKey: roleQueryKeys.list,
    queryFn: ({ signal }) => listRoleDetails(signal),
  });
  const permissions = useQuery({
    queryKey: roleQueryKeys.permissions,
    queryFn: ({ signal }) => listPermissions(signal),
    staleTime: 5 * 60_000,
  });
  const [selectedId, setSelectedId] = useState<string | null>(null);

  if (roles.isPending || permissions.isPending) {
    return (
      <div className="grid gap-4 lg:grid-cols-[16rem_minmax(0,1fr)]" aria-busy="true">
        <Skeleton className="h-72 rounded-xl" />
        <Skeleton className="h-96 rounded-xl" />
      </div>
    );
  }
  const error = roles.error ?? permissions.error;
  if (error || !roles.data || !permissions.data) {
    return (
      <ErrorState
        message={error?.message ?? "โหลดข้อมูลไม่สำเร็จ"}
        requestId={error instanceof ApiError ? error.requestId : null}
        onRetry={() => {
          void roles.refetch();
          void permissions.refetch();
        }}
        retrying={roles.isFetching || permissions.isFetching}
      />
    );
  }

  const role = roles.data.find((r) => r.id === selectedId) ?? roles.data[0];
  return (
    <div className="grid gap-4 lg:grid-cols-[16rem_minmax(0,1fr)]">
      <Card className="h-fit">
        <CardHeader className="flex flex-row items-center justify-between gap-2">
          <CardTitle className="text-base">บทบาท</CardTitle>
          {canManage ? <CreateRoleDialog onCreated={(r) => setSelectedId(r.id)} /> : null}
        </CardHeader>
        <CardContent className="px-2">
          <ul className="space-y-0.5" aria-label="รายการบทบาท">
            {roles.data.map((r) => (
              <li key={r.id}>
                <button
                  type="button"
                  aria-current={r.id === role?.id ? "true" : undefined}
                  onClick={() => setSelectedId(r.id)}
                  className={cn(
                    "hover:bg-muted flex w-full items-center justify-between gap-2 rounded-md px-3 py-2 text-left text-sm",
                    r.id === role?.id && "bg-muted font-medium",
                  )}
                >
                  <span className="truncate">{roleLabel(r.code, r.name)}</span>
                  <span className="text-muted-foreground shrink-0 text-xs tabular-nums">
                    {r.is_locked ? "ทั้งหมด" : r.permissions.length}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>

      {role ? (
        <Card>
          <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-3">
            <div className="space-y-1.5">
              <CardTitle className="flex flex-wrap items-center gap-2">
                <ShieldCheck className="text-primary size-5" aria-hidden />
                {roleLabel(role.code, role.name)}
                <Badge variant="secondary" className="font-mono">
                  {role.code}
                </Badge>
                {role.is_system ? <Badge variant="outline">บทบาทของระบบ</Badge> : null}
              </CardTitle>
              <CardDescription>
                สิทธิ์ที่เปลี่ยนมีผลกับผู้ใช้ทุกคนที่มีบทบาทนี้ทันที และถูกบันทึกในบันทึกการใช้งาน
              </CardDescription>
            </div>
            {canManage && !role.is_system ? (
              <DeleteRoleDialog role={role} onDeleted={() => setSelectedId(null)} />
            ) : null}
          </CardHeader>
          <CardContent className="space-y-6">
            {/* Keyed by the saved values: the forms start fresh whenever the role changes. */}
            <RoleDetailsForm
              key={`${role.id}:${role.name}:${role.description}`}
              role={role}
              canManage={canManage && !role.is_system}
            />
            <PermissionEditor
              key={`${role.id}:${role.permissions.join(",")}`}
              role={role}
              permissions={permissions.data}
              canManage={canManage}
            />
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
