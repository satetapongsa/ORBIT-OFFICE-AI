"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Building2, Loader2, Pencil, Power, ShieldCheck, UserPlus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useId, useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { FormField } from "@/components/common/form-field";
import { NativeSelect } from "@/components/common/native-select";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
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
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useRoles } from "@/features/documents/hooks/use-documents";
import {
  useCreateAccount,
  useDepartmentsFull,
  useEmployeeList,
  useSaveDepartment,
  useSetActive,
  useSetRoles,
  useUpdateAccount,
} from "@/features/employees/hooks/use-employees";
import { EMPLOYMENT_STATUS_LABELS } from "@/features/employees/labels";
import { ApiError } from "@/services/api-client";
import {
  employmentStatusSchema,
  type AccountInput,
  type Department,
  type EmployeeProfile,
} from "@/services/employees";

export function ApiErrorAlert({ error }: { error: unknown }) {
  if (!(error instanceof ApiError)) return null;
  return (
    <Alert variant="destructive">
      <AlertDescription>
        {error.message}
        {error.details.length > 0 ? (
          <ul className="mt-1 list-disc pl-4">
            {error.details.map((d, i) => (
              <li key={`${d.field}-${i}`}>{d.message}</li>
            ))}
          </ul>
        ) : null}
      </AlertDescription>
    </Alert>
  );
}

/** Mirrors backend `UserCreate` / `UserUpdate` limits. */
const accountSchema = z.object({
  employee_code: z
    .string()
    .trim()
    .regex(/^[A-Za-z0-9_-]{1,32}$/, "ใช้ตัวอักษรอังกฤษ ตัวเลข - หรือ _ ไม่เกิน 32 ตัว"),
  email: z.string().trim().email("รูปแบบอีเมลไม่ถูกต้อง"),
  first_name: z.string().trim().min(1, "กรุณาระบุชื่อ").max(100),
  last_name: z.string().trim().min(1, "กรุณาระบุนามสกุล").max(100),
  display_name: z.string().trim().max(200),
  department_id: z.string(),
  job_title: z.string().trim().max(200),
  phone_work: z.string().trim().max(50),
  employment_status: employmentStatusSchema,
  password: z.string().max(256),
});
type AccountValues = z.infer<typeof accountSchema>;

function toInput(v: AccountValues): AccountInput {
  return {
    employee_code: v.employee_code,
    email: v.email,
    first_name: v.first_name,
    last_name: v.last_name,
    display_name: v.display_name || `${v.first_name} ${v.last_name}`,
    department_id: v.department_id || null,
    job_title: v.job_title || null,
    phone_work: v.phone_work || null,
    employment_status: v.employment_status,
  };
}

function AccountFields({
  form,
  withPassword,
}: {
  form: ReturnType<typeof useForm<AccountValues>>;
  withPassword: boolean;
}) {
  const ids = { department: useId(), status: useId() };
  const departments = useDepartmentsFull();
  const e = form.formState.errors;
  return (
    <>
      <div className="grid gap-4 sm:grid-cols-2">
        <FormField label="ชื่อ" registration={form.register("first_name")} error={e.first_name} />
        <FormField label="นามสกุล" registration={form.register("last_name")} error={e.last_name} />
      </div>
      <FormField
        label="ชื่อที่แสดง"
        hint="เว้นว่างเพื่อใช้ชื่อและนามสกุล"
        registration={form.register("display_name")}
        error={e.display_name}
      />
      <div className="grid gap-4 sm:grid-cols-2">
        <FormField
          label="รหัสพนักงาน"
          registration={form.register("employee_code")}
          error={e.employee_code}
        />
        <FormField
          label="อีเมลที่ทำงาน"
          type="email"
          autoComplete="off"
          registration={form.register("email")}
          error={e.email}
        />
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <FormField label="ตำแหน่ง" registration={form.register("job_title")} error={e.job_title} />
        <FormField
          label="เบอร์โทรที่ทำงาน"
          registration={form.register("phone_work")}
          error={e.phone_work}
        />
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor={ids.department}>แผนก</Label>
          <NativeSelect id={ids.department} {...form.register("department_id")}>
            <option value="">ไม่ระบุแผนก</option>
            {(departments.data ?? []).map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </NativeSelect>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor={ids.status}>สถานะการจ้างงาน</Label>
          <NativeSelect id={ids.status} {...form.register("employment_status")}>
            {employmentStatusSchema.options.map((s) => (
              <option key={s} value={s}>
                {EMPLOYMENT_STATUS_LABELS[s]}
              </option>
            ))}
          </NativeSelect>
        </div>
      </div>
      {withPassword ? (
        <FormField
          label="รหัสผ่านเริ่มต้น (ไม่บังคับ)"
          type="password"
          autoComplete="new-password"
          hint="เว้นว่างได้ พนักงานจะตั้งรหัสผ่านเองผ่านลิงก์ลืมรหัสผ่าน"
          registration={form.register("password")}
          error={e.password}
        />
      ) : null}
    </>
  );
}

export function CreateEmployeeDialog() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const create = useCreateAccount();
  const form = useForm<AccountValues>({
    resolver: zodResolver(accountSchema),
    defaultValues: {
      employee_code: "",
      email: "",
      first_name: "",
      last_name: "",
      display_name: "",
      department_id: "",
      job_title: "",
      phone_work: "",
      employment_status: "ACTIVE",
      password: "",
    },
  });
  const close = () => {
    setOpen(false);
    form.reset();
    create.reset();
  };
  const onSubmit = form.handleSubmit((v) =>
    create.mutate(
      { ...toInput(v), ...(v.password ? { password: v.password } : {}) },
      {
        onSuccess: (user) => {
          toast.success(`เพิ่มพนักงาน ${user.display_name} แล้ว`);
          close();
          router.push(`/employees/${user.id}`);
        },
      },
    ),
  );
  return (
    <Dialog open={open} onOpenChange={(next) => (next ? setOpen(true) : close())}>
      <DialogTrigger asChild>
        <Button>
          <UserPlus aria-hidden />
          เพิ่มพนักงาน
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>เพิ่มพนักงาน</DialogTitle>
          <DialogDescription>
            บัญชีใหม่ได้รับบทบาท “พนักงาน” ผู้ที่มีสิทธิ์กำหนดบทบาทเปลี่ยนภายหลังได้
          </DialogDescription>
        </DialogHeader>
        <form noValidate onSubmit={onSubmit} className="space-y-4" aria-label="ฟอร์มเพิ่มพนักงาน">
          <ApiErrorAlert error={create.error} />
          <AccountFields form={form} withPassword />
          <DialogFooter>
            <Button type="submit" disabled={create.isPending}>
              {create.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
              เพิ่มพนักงาน
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function EditAccountDialog({ employee }: { employee: EmployeeProfile }) {
  const [open, setOpen] = useState(false);
  const update = useUpdateAccount(employee.id);
  const form = useForm<AccountValues>({
    resolver: zodResolver(accountSchema),
    values: {
      employee_code: employee.employee_code,
      email: employee.email,
      first_name: employee.first_name,
      last_name: employee.last_name,
      display_name: employee.display_name,
      department_id: employee.department?.id ?? "",
      job_title: employee.job_title ?? "",
      phone_work: employee.phone_work ?? "",
      employment_status: employee.account?.employment_status ?? "ACTIVE",
      password: "",
    },
  });
  const onSubmit = form.handleSubmit((v) =>
    update.mutate(toInput(v), {
      onSuccess: () => {
        toast.success("บันทึกข้อมูลบัญชีแล้ว");
        setOpen(false);
      },
    }),
  );
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) update.reset();
      }}
    >
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          <Pencil aria-hidden />
          แก้ไขข้อมูล
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>แก้ไขข้อมูลพนักงาน</DialogTitle>
          <DialogDescription>พนักงานจะได้รับการแจ้งเตือนว่าข้อมูลใดถูกเปลี่ยน</DialogDescription>
        </DialogHeader>
        <form noValidate onSubmit={onSubmit} className="space-y-4" aria-label="ฟอร์มแก้ไขพนักงาน">
          <ApiErrorAlert error={update.error} />
          <AccountFields form={form} withPassword={false} />
          <DialogFooter>
            <Button type="submit" disabled={update.isPending}>
              {update.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
              บันทึก
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function RolesDialog({ employee }: { employee: EmployeeProfile }) {
  const [open, setOpen] = useState(false);
  const current = employee.account?.roles.map((r) => r.code) ?? [];
  const [selected, setSelected] = useState<string[]>(current);
  const roles = useRoles(open);
  const save = useSetRoles(employee.id);
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next) setSelected(current);
        else save.reset();
      }}
    >
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          <ShieldCheck aria-hidden />
          กำหนดบทบาท
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-md">
        <DialogHeader>
          <DialogTitle>บทบาทของ {employee.display_name}</DialogTitle>
          <DialogDescription>
            ให้หรือถอนได้เฉพาะบทบาทที่คุณมีสิทธิ์ครบทุกข้อ สิทธิ์ใหม่มีผลทันที
          </DialogDescription>
        </DialogHeader>
        <ApiErrorAlert error={save.error} />
        {roles.isPending ? (
          <Loader2 className="text-muted-foreground mx-auto animate-spin" aria-label="กำลังโหลด" />
        ) : (
          <fieldset className="space-y-2">
            <legend className="sr-only">บทบาท</legend>
            {(roles.data ?? []).map((r) => (
              <label key={r.id} className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  className="size-4"
                  checked={selected.includes(r.code)}
                  onChange={(e) =>
                    setSelected((s) =>
                      e.target.checked ? [...s, r.code] : s.filter((c) => c !== r.code),
                    )
                  }
                />
                {r.name} <span className="text-muted-foreground text-xs">({r.code})</span>
              </label>
            ))}
          </fieldset>
        )}
        <DialogFooter>
          <Button
            disabled={save.isPending}
            onClick={() =>
              save.mutate(selected, {
                onSuccess: () => {
                  toast.success("บันทึกบทบาทแล้ว");
                  setOpen(false);
                },
              })
            }
          >
            {save.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
            บันทึก
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function ActiveToggleDialog({ employee }: { employee: EmployeeProfile }) {
  const toggle = useSetActive(employee.id);
  const deactivate = employee.is_active;
  return (
    <Dialog onOpenChange={(open) => !open && toggle.reset()}>
      <DialogTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          className={deactivate ? "text-destructive hover:text-destructive" : undefined}
        >
          <Power aria-hidden />
          {deactivate ? "ระงับบัญชี" : "เปิดใช้งานบัญชี"}
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>
            {deactivate ? "ระงับบัญชี" : "เปิดใช้งานบัญชี"} {employee.display_name}?
          </DialogTitle>
          <DialogDescription>
            {deactivate
              ? "พนักงานจะถูกออกจากระบบทุกอุปกรณ์ทันทีและเข้าสู่ระบบไม่ได้จนกว่าจะเปิดใช้งานอีกครั้ง"
              : "พนักงานจะเข้าสู่ระบบได้ตามปกติและได้รับการแจ้งเตือน"}
          </DialogDescription>
        </DialogHeader>
        <ApiErrorAlert error={toggle.error} />
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="outline">ยกเลิก</Button>
          </DialogClose>
          <Button
            variant={deactivate ? "destructive" : "default"}
            disabled={toggle.isPending}
            onClick={() =>
              toggle.mutate(!deactivate, {
                onSuccess: () =>
                  toast.success(deactivate ? "ระงับบัญชีแล้ว" : "เปิดใช้งานบัญชีแล้ว"),
              })
            }
          >
            {toggle.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
            {deactivate ? "ระงับบัญชี" : "เปิดใช้งาน"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** Mirrors backend `DepartmentCreate` / `DepartmentUpdate`. */
const departmentFormSchema = z.object({
  code: z
    .string()
    .trim()
    .regex(/^[A-Za-z0-9_-]{1,32}$/, "ใช้ตัวอักษรอังกฤษ ตัวเลข - หรือ _ ไม่เกิน 32 ตัว"),
  name: z.string().trim().min(1, "กรุณาระบุชื่อแผนก").max(200),
  description: z.string().trim().max(2000),
  manager_id: z.string(),
});
type DepartmentValues = z.infer<typeof departmentFormSchema>;

export function DepartmentDialog({ department }: { department?: Department }) {
  const [open, setOpen] = useState(false);
  const ids = { description: useId(), manager: useId() };
  const save = useSaveDepartment(department?.id ?? null);
  const members = useEmployeeList(
    { departmentId: department?.id, pageSize: 100 },
    open && Boolean(department),
  );
  const form = useForm<DepartmentValues>({
    resolver: zodResolver(departmentFormSchema),
    values: {
      code: department?.code ?? "",
      name: department?.name ?? "",
      description: department?.description ?? "",
      manager_id: department?.manager_id ?? "",
    },
  });
  const onSubmit = form.handleSubmit((v) =>
    save.mutate(
      {
        code: v.code,
        name: v.name,
        description: v.description || null,
        manager_id: v.manager_id || null,
      },
      {
        onSuccess: () => {
          toast.success(department ? "บันทึกแผนกแล้ว" : "เพิ่มแผนกแล้ว");
          setOpen(false);
          if (!department) form.reset();
        },
      },
    ),
  );
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) save.reset();
      }}
    >
      <DialogTrigger asChild>
        {department ? (
          <Button variant="ghost" size="sm" aria-label={`แก้ไขแผนก ${department.name}`}>
            <Pencil aria-hidden />
          </Button>
        ) : (
          <Button variant="outline">
            <Building2 aria-hidden />
            เพิ่มแผนก
          </Button>
        )}
      </DialogTrigger>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{department ? `แก้ไขแผนก ${department.name}` : "เพิ่มแผนก"}</DialogTitle>
          <DialogDescription>หัวหน้าแผนกเลือกได้จากพนักงานในแผนกนั้น</DialogDescription>
        </DialogHeader>
        <form noValidate onSubmit={onSubmit} className="space-y-4" aria-label="ฟอร์มแผนก">
          <ApiErrorAlert error={save.error} />
          <div className="grid gap-4 sm:grid-cols-[8rem_minmax(0,1fr)]">
            <FormField
              label="รหัส"
              registration={form.register("code")}
              error={form.formState.errors.code}
            />
            <FormField
              label="ชื่อแผนก"
              registration={form.register("name")}
              error={form.formState.errors.name}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor={ids.description}>คำอธิบาย</Label>
            <Textarea id={ids.description} rows={3} {...form.register("description")} />
          </div>
          {department ? (
            <div className="space-y-1.5">
              <Label htmlFor={ids.manager}>หัวหน้าแผนก</Label>
              <NativeSelect id={ids.manager} {...form.register("manager_id")}>
                <option value="">ไม่ระบุ</option>
                {(members.data?.items ?? []).map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.display_name}
                  </option>
                ))}
              </NativeSelect>
            </div>
          ) : null}
          <DialogFooter>
            <Button type="submit" disabled={save.isPending}>
              {save.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
              บันทึก
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
