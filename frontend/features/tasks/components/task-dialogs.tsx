"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2, Pencil, Plus, Trash2, Users } from "lucide-react";
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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useSession } from "@/features/auth/hooks/use-session";
import { AssigneePicker, type PickedUser } from "@/features/tasks/components/assignee-picker";
import {
  useCreateTask,
  useDeleteTask,
  useReplaceAssignees,
  useUpdateTask,
} from "@/features/tasks/hooks/use-tasks";
import { TASK_PRIORITY_LABELS, dueDateToIso, isoToDueDate } from "@/features/tasks/labels";
import { ApiError } from "@/services/api-client";
import { taskPrioritySchema, type TaskDetail } from "@/services/tasks";

/** Mirrors backend `TaskCreate` / `TaskUpdate` limits. */
export const taskFormSchema = z.object({
  title: z.string().trim().min(1, "กรุณาระบุชื่องาน").max(300, "ชื่องานยาวเกิน 300 ตัวอักษร"),
  description: z.string().trim().max(10_000, "รายละเอียดยาวเกิน 10,000 ตัวอักษร"),
  priority: taskPrioritySchema,
  due: z.string().regex(/^(\d{4}-\d{2}-\d{2})?$/, "รูปแบบวันที่ไม่ถูกต้อง"),
});
type TaskFormValues = z.infer<typeof taskFormSchema>;

function ErrorAlert({ error }: { error: unknown }) {
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

function TaskFields({ form }: { form: ReturnType<typeof useForm<TaskFormValues>> }) {
  const ids = { description: useId(), priority: useId(), due: useId() };
  const errors = form.formState.errors;
  return (
    <>
      <FormField label="ชื่องาน" registration={form.register("title")} error={errors.title} />
      <div className="space-y-1.5">
        <Label htmlFor={ids.description}>รายละเอียด</Label>
        <Textarea id={ids.description} rows={4} {...form.register("description")} />
        {errors.description ? (
          <p role="alert" className="text-destructive text-xs">
            {errors.description.message}
          </p>
        ) : null}
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor={ids.priority}>ความสำคัญ</Label>
          <NativeSelect id={ids.priority} {...form.register("priority")}>
            {taskPrioritySchema.options.map((p) => (
              <option key={p} value={p}>
                {TASK_PRIORITY_LABELS[p]}
              </option>
            ))}
          </NativeSelect>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor={ids.due}>กำหนดส่ง</Label>
          <Input id={ids.due} type="date" {...form.register("due")} />
          {errors.due ? (
            <p role="alert" className="text-destructive text-xs">
              {errors.due.message}
            </p>
          ) : null}
        </div>
      </div>
    </>
  );
}

export function CreateTaskDialog() {
  const router = useRouter();
  const { has } = useSession();
  const [open, setOpen] = useState(false);
  const [assignees, setAssignees] = useState<PickedUser[]>([]);
  const create = useCreateTask();
  const canAssign = has("tasks:assign");
  const form = useForm<TaskFormValues>({
    resolver: zodResolver(taskFormSchema),
    defaultValues: { title: "", description: "", priority: "MEDIUM", due: "" },
  });

  const close = () => {
    setOpen(false);
    form.reset();
    setAssignees([]);
    create.reset();
  };

  const onSubmit = form.handleSubmit((v) => {
    create.mutate(
      {
        title: v.title,
        description: v.description || null,
        priority: v.priority,
        due_at: dueDateToIso(v.due),
        assignee_ids: assignees.map((a) => a.id),
      },
      {
        onSuccess: (task) => {
          toast.success("สร้างงานแล้ว");
          close();
          router.push(`/tasks/${task.id}`);
        },
      },
    );
  });

  return (
    <Dialog open={open} onOpenChange={(next) => (next ? setOpen(true) : close())}>
      <DialogTrigger asChild>
        <Button>
          <Plus aria-hidden />
          สร้างงาน
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>สร้างงานใหม่</DialogTitle>
          <DialogDescription>
            งานจะอยู่ในแผนกของคุณ ผู้จัดการแผนกจะเห็นและติดตามงานนี้ได้
          </DialogDescription>
        </DialogHeader>
        <form noValidate onSubmit={onSubmit} className="space-y-4" aria-label="ฟอร์มสร้างงาน">
          <ErrorAlert error={create.error} />
          <TaskFields form={form} />
          {canAssign ? (
            <AssigneePicker value={assignees} onChange={setAssignees} disabled={create.isPending} />
          ) : (
            <p className="text-muted-foreground text-xs">งานนี้จะมอบหมายให้คุณเอง</p>
          )}
          <DialogFooter>
            <Button type="submit" disabled={create.isPending}>
              {create.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
              สร้างงาน
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function EditTaskDialog({ task }: { task: TaskDetail }) {
  const [open, setOpen] = useState(false);
  const update = useUpdateTask(task.id);
  const form = useForm<TaskFormValues>({
    resolver: zodResolver(taskFormSchema),
    values: {
      title: task.title,
      description: task.description ?? "",
      priority: task.priority,
      due: isoToDueDate(task.due_at),
    },
  });

  const onSubmit = form.handleSubmit((v) => {
    const due = isoToDueDate(task.due_at) === v.due ? undefined : dueDateToIso(v.due);
    update.mutate(
      {
        title: v.title,
        description: v.description || null,
        priority: v.priority,
        ...(due !== undefined ? { due_at: due } : {}),
      },
      {
        onSuccess: () => {
          toast.success("บันทึกงานแล้ว");
          setOpen(false);
        },
      },
    );
  });

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) update.reset();
      }}
    >
      <DialogTrigger asChild>
        <Button variant="outline">
          <Pencil aria-hidden />
          แก้ไข
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>แก้ไขงาน</DialogTitle>
          <DialogDescription>การแก้ไขจะถูกบันทึกในประวัติของงาน</DialogDescription>
        </DialogHeader>
        <form noValidate onSubmit={onSubmit} className="space-y-4" aria-label="ฟอร์มแก้ไขงาน">
          <ErrorAlert error={update.error} />
          <TaskFields form={form} />
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

export function AssigneesDialog({ task }: { task: TaskDetail }) {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState<PickedUser[]>(task.assignees);
  const replace = useReplaceAssignees(task.id);
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next) setValue(task.assignees);
        else replace.reset();
      }}
    >
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          <Users aria-hidden />
          จัดการผู้รับผิดชอบ
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-md">
        <DialogHeader>
          <DialogTitle>ผู้รับผิดชอบงาน</DialogTitle>
          <DialogDescription>ผู้ที่ถูกเพิ่มจะได้รับการแจ้งเตือน</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <ErrorAlert error={replace.error} />
          <AssigneePicker value={value} onChange={setValue} disabled={replace.isPending} />
        </div>
        <DialogFooter>
          <Button
            disabled={replace.isPending || value.length === 0}
            onClick={() =>
              replace.mutate(
                value.map((u) => u.id),
                {
                  onSuccess: () => {
                    toast.success("บันทึกผู้รับผิดชอบแล้ว");
                    setOpen(false);
                  },
                },
              )
            }
          >
            {replace.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
            บันทึก
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function DeleteTaskDialog({ task }: { task: TaskDetail }) {
  const router = useRouter();
  const remove = useDeleteTask(task.id);
  return (
    <Dialog onOpenChange={(open) => !open && remove.reset()}>
      <DialogTrigger asChild>
        <Button variant="outline" className="text-destructive hover:text-destructive">
          <Trash2 aria-hidden />
          ลบงาน
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>ลบงาน “{task.title}”?</DialogTitle>
          <DialogDescription>
            งานจะหายไปจากรายการของทุกคน ผู้ดูแลระบบยังตรวจสอบได้จากบันทึกการใช้งาน
          </DialogDescription>
        </DialogHeader>
        <ErrorAlert error={remove.error} />
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="outline">ยกเลิก</Button>
          </DialogClose>
          <Button
            variant="destructive"
            disabled={remove.isPending}
            onClick={() =>
              remove.mutate(undefined, {
                onSuccess: () => {
                  toast.success("ลบงานแล้ว");
                  router.replace("/tasks");
                },
              })
            }
          >
            {remove.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
            ลบงาน
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
