"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Eye, Loader2, LockKeyhole, Pencil } from "lucide-react";
import { useId, useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { FormField } from "@/components/common/form-field";
import { NativeSelect } from "@/components/common/native-select";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
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
import { ApiErrorAlert } from "@/features/employees/components/account-dialogs";
import { useHrProfile, useReplaceHrProfile } from "@/features/employees/hooks/use-employees";
import { EMPLOYMENT_TYPE_LABELS, formatThaiDate } from "@/features/employees/labels";
import { formatDateTime } from "@/lib/format";
import {
  employmentTypeSchema,
  type EmployeeProfile,
  type HrProfile,
  type HrProfileInput,
} from "@/services/employees";

/** Mirrors backend `HrProfileIn`. Only the last 4 digits of the national ID are ever stored. */
const hrFormSchema = z
  .object({
    date_of_birth: z.string(),
    national_id_last4: z.string().regex(/^(\d{4})?$/, "ระบุเฉพาะเลข 4 หลักสุดท้าย"),
    personal_phone: z.string().trim().max(50),
    personal_email: z.union([z.literal(""), z.string().trim().email("รูปแบบอีเมลไม่ถูกต้อง")]),
    address: z.string().trim().max(1000),
    hire_date: z.string(),
    employment_type: z.union([z.literal(""), employmentTypeSchema]),
    contact_name: z.string().trim().max(200),
    contact_relationship: z.string().trim().max(100),
    contact_phone: z.string().trim().max(50),
  })
  .refine(
    (v) => {
      const parts = [v.contact_name, v.contact_relationship, v.contact_phone].filter(Boolean);
      return parts.length === 0 || parts.length === 3;
    },
    {
      message: "กรอกผู้ติดต่อฉุกเฉินให้ครบทั้ง 3 ช่อง หรือเว้นว่างทั้งหมด",
      path: ["contact_name"],
    },
  );
type HrValues = z.infer<typeof hrFormSchema>;

function toValues(hr: HrProfile): HrValues {
  return {
    date_of_birth: hr.date_of_birth ?? "",
    national_id_last4: hr.national_id_last4 ?? "",
    personal_phone: hr.personal_phone ?? "",
    personal_email: hr.personal_email ?? "",
    address: hr.address ?? "",
    hire_date: hr.hire_date ?? "",
    employment_type: hr.employment_type ?? "",
    contact_name: hr.emergency_contact?.name ?? "",
    contact_relationship: hr.emergency_contact?.relationship ?? "",
    contact_phone: hr.emergency_contact?.phone ?? "",
  };
}

function toInput(v: HrValues): HrProfileInput {
  return {
    date_of_birth: v.date_of_birth || null,
    national_id_last4: v.national_id_last4 || null,
    personal_phone: v.personal_phone || null,
    personal_email: v.personal_email || null,
    address: v.address || null,
    hire_date: v.hire_date || null,
    employment_type: v.employment_type || null,
    emergency_contact: v.contact_name
      ? { name: v.contact_name, relationship: v.contact_relationship, phone: v.contact_phone }
      : null,
  };
}

function EditHrDialog({ employeeId, hr }: { employeeId: string; hr: HrProfile }) {
  const [open, setOpen] = useState(false);
  const ids = { dob: useId(), hire: useId(), type: useId(), address: useId() };
  const save = useReplaceHrProfile(employeeId);
  const form = useForm<HrValues>({ resolver: zodResolver(hrFormSchema), values: toValues(hr) });
  const e = form.formState.errors;
  const onSubmit = form.handleSubmit((v) =>
    save.mutate(toInput(v), {
      onSuccess: () => {
        toast.success("บันทึกข้อมูลบุคคลแล้ว");
        setOpen(false);
      },
    }),
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
        <Button variant="outline" size="sm">
          <Pencil aria-hidden />
          แก้ไข
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>แก้ไขข้อมูลบุคคล</DialogTitle>
          <DialogDescription>
            ข้อมูลส่วนนี้เป็นความลับ บันทึกการใช้งานเก็บเฉพาะชื่อช่องที่แก้ไข ไม่เก็บค่าข้อมูล
          </DialogDescription>
        </DialogHeader>
        <form noValidate onSubmit={onSubmit} className="space-y-4" aria-label="ฟอร์มข้อมูลบุคคล">
          <ApiErrorAlert error={save.error} />
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor={ids.dob}>วันเกิด</Label>
              <Input id={ids.dob} type="date" {...form.register("date_of_birth")} />
            </div>
            <FormField
              label="เลขบัตรประชาชน 4 หลักสุดท้าย"
              inputMode="numeric"
              maxLength={4}
              autoComplete="off"
              registration={form.register("national_id_last4")}
              error={e.national_id_last4}
            />
            <div className="space-y-1.5">
              <Label htmlFor={ids.hire}>วันเริ่มงาน</Label>
              <Input id={ids.hire} type="date" {...form.register("hire_date")} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor={ids.type}>ประเภทการจ้าง</Label>
              <NativeSelect id={ids.type} {...form.register("employment_type")}>
                <option value="">ไม่ระบุ</option>
                {employmentTypeSchema.options.map((t) => (
                  <option key={t} value={t}>
                    {EMPLOYMENT_TYPE_LABELS[t]}
                  </option>
                ))}
              </NativeSelect>
            </div>
            <FormField
              label="เบอร์โทรส่วนตัว"
              autoComplete="off"
              registration={form.register("personal_phone")}
              error={e.personal_phone}
            />
            <FormField
              label="อีเมลส่วนตัว"
              type="email"
              autoComplete="off"
              registration={form.register("personal_email")}
              error={e.personal_email}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor={ids.address}>ที่อยู่</Label>
            <Textarea id={ids.address} rows={2} {...form.register("address")} />
          </div>
          <fieldset className="grid gap-4 sm:grid-cols-3">
            <legend className="mb-2 text-sm font-medium">ผู้ติดต่อฉุกเฉิน</legend>
            <FormField
              label="ชื่อ"
              registration={form.register("contact_name")}
              error={e.contact_name}
            />
            <FormField label="ความสัมพันธ์" registration={form.register("contact_relationship")} />
            <FormField label="เบอร์โทร" registration={form.register("contact_phone")} />
          </fieldset>
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

function Row({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <>
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="break-words">{value || "—"}</dd>
    </>
  );
}

/**
 * Sensitive HR data. Someone else's record is loaded only after an explicit click because
 * each read is written to the audit log.
 */
export function HrProfileCard({
  employee,
  isSelf,
}: {
  employee: EmployeeProfile;
  isSelf: boolean;
}) {
  const [revealed, setRevealed] = useState(isSelf);
  const hr = useHrProfile(employee.id, revealed);
  const canEdit = employee.capabilities.can_edit_hr;

  return (
    <Card data-testid="hr-card">
      <CardHeader className="flex flex-row items-start justify-between gap-2">
        <div className="space-y-1.5">
          <CardTitle className="flex items-center gap-2">
            <LockKeyhole className="size-4" aria-hidden />
            ข้อมูลบุคคล (ความลับ)
          </CardTitle>
          <CardDescription>
            {isSelf
              ? "ข้อมูลของคุณที่ฝ่ายบุคคลบันทึกไว้ หากไม่ถูกต้องกรุณาติดต่อฝ่ายบุคคล"
              : "การเปิดดูข้อมูลส่วนนี้จะถูกบันทึกในบันทึกการใช้งาน"}
          </CardDescription>
        </div>
        {revealed && hr.data && canEdit ? (
          <EditHrDialog employeeId={employee.id} hr={hr.data} />
        ) : null}
      </CardHeader>
      <CardContent>
        {!revealed ? (
          <Button variant="outline" onClick={() => setRevealed(true)}>
            <Eye aria-hidden />
            แสดงข้อมูลบุคคล
          </Button>
        ) : hr.isPending ? (
          <Skeleton className="h-32 w-full" />
        ) : hr.isError ? (
          <p className="text-destructive text-sm">{hr.error.message}</p>
        ) : !hr.data.exists ? (
          <p className="text-muted-foreground text-sm">ยังไม่มีการบันทึกข้อมูลบุคคล</p>
        ) : (
          <dl className="grid grid-cols-[9rem_minmax(0,1fr)] gap-x-3 gap-y-2 text-sm">
            <Row
              label="วันเกิด"
              value={hr.data.date_of_birth ? formatThaiDate(hr.data.date_of_birth) : null}
            />
            <Row
              label="เลขบัตรประชาชน"
              value={hr.data.national_id_last4 ? `•••• •••• ${hr.data.national_id_last4}` : null}
            />
            <Row
              label="วันเริ่มงาน"
              value={hr.data.hire_date ? formatThaiDate(hr.data.hire_date) : null}
            />
            <Row
              label="ประเภทการจ้าง"
              value={
                hr.data.employment_type ? EMPLOYMENT_TYPE_LABELS[hr.data.employment_type] : null
              }
            />
            <Row label="เบอร์โทรส่วนตัว" value={hr.data.personal_phone} />
            <Row label="อีเมลส่วนตัว" value={hr.data.personal_email} />
            <Row label="ที่อยู่" value={hr.data.address} />
            <Row
              label="ผู้ติดต่อฉุกเฉิน"
              value={
                hr.data.emergency_contact
                  ? `${hr.data.emergency_contact.name} (${hr.data.emergency_contact.relationship}) ${hr.data.emergency_contact.phone}`
                  : null
              }
            />
            {hr.data.updated_at ? (
              <p className="text-muted-foreground col-span-2 pt-2 text-xs">
                ปรับปรุงล่าสุด {formatDateTime(hr.data.updated_at)}
                {hr.data.updated_by ? ` โดย ${hr.data.updated_by.display_name}` : ""}
              </p>
            ) : null}
          </dl>
        )}
      </CardContent>
    </Card>
  );
}
