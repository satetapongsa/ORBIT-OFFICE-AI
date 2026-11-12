"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2, Plus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useId, useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { FormField } from "@/components/common/form-field";
import { NativeSelect } from "@/components/common/native-select";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ApiErrorAlert } from "@/features/employees/components/account-dialogs";
import { useCreateTicket } from "@/features/helpdesk/hooks/use-tickets";
import { TICKET_CATEGORY_LABELS } from "@/features/helpdesk/labels";
import { TASK_PRIORITY_LABELS } from "@/features/tasks/labels";
import { taskPrioritySchema } from "@/services/tasks";
import { ticketCategorySchema } from "@/services/tickets";

/** Mirrors backend `TicketCreate` limits. */
export const ticketFormSchema = z.object({
  title: z.string().trim().min(1, "กรุณาระบุเรื่อง").max(300, "เรื่องยาวเกิน 300 ตัวอักษร"),
  description: z
    .string()
    .trim()
    .min(1, "กรุณาอธิบายปัญหา")
    .max(5000, "รายละเอียดยาวเกิน 5,000 ตัวอักษร"),
  category: ticketCategorySchema,
  priority: taskPrioritySchema,
});
type TicketFormValues = z.infer<typeof ticketFormSchema>;

export function CreateTicketDialog() {
  const router = useRouter();
  const ids = { description: useId(), category: useId(), priority: useId() };
  const [open, setOpen] = useState(false);
  const create = useCreateTicket();
  const form = useForm<TicketFormValues>({
    resolver: zodResolver(ticketFormSchema),
    defaultValues: { title: "", description: "", category: "OTHER", priority: "MEDIUM" },
  });
  const errors = form.formState.errors;

  const close = () => {
    setOpen(false);
    form.reset();
    create.reset();
  };

  const onSubmit = form.handleSubmit((values) =>
    create.mutate(values, {
      onSuccess: (ticket) => {
        toast.success(`แจ้งปัญหาแล้ว เลขที่ ${ticket.ticket_number}`);
        close();
        router.push(`/helpdesk/${ticket.id}`);
      },
    }),
  );

  return (
    <Dialog open={open} onOpenChange={(next) => (next ? setOpen(true) : close())}>
      <DialogTrigger asChild>
        <Button>
          <Plus aria-hidden />
          แจ้งปัญหาใหม่
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>แจ้งปัญหาไอที</DialogTitle>
          <DialogDescription>
            ทีมไอทีจะได้รับแจ้งทันที และคุณจะได้รับการแจ้งเตือนเมื่อมีความคืบหน้า
          </DialogDescription>
        </DialogHeader>
        <form noValidate onSubmit={onSubmit} className="space-y-4" aria-label="ฟอร์มแจ้งปัญหา">
          <ApiErrorAlert error={create.error} />
          <FormField
            label="เรื่อง"
            placeholder="เช่น เครื่องพิมพ์ชั้น 3 พิมพ์ไม่ออก"
            registration={form.register("title")}
            error={errors.title}
          />
          <div className="space-y-1.5">
            <Label htmlFor={ids.description}>รายละเอียด</Label>
            <Textarea
              id={ids.description}
              rows={5}
              placeholder="เกิดอะไรขึ้น เริ่มเมื่อไร ลองแก้อะไรไปแล้วบ้าง"
              aria-invalid={errors.description ? true : undefined}
              {...form.register("description")}
            />
            {errors.description ? (
              <p role="alert" className="text-destructive text-xs">
                {errors.description.message}
              </p>
            ) : null}
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor={ids.category}>หมวด</Label>
              <NativeSelect id={ids.category} {...form.register("category")}>
                {ticketCategorySchema.options.map((c) => (
                  <option key={c} value={c}>
                    {TICKET_CATEGORY_LABELS[c]}
                  </option>
                ))}
              </NativeSelect>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor={ids.priority}>ความเร่งด่วน</Label>
              <NativeSelect id={ids.priority} {...form.register("priority")}>
                {taskPrioritySchema.options.map((p) => (
                  <option key={p} value={p}>
                    {TASK_PRIORITY_LABELS[p]}
                  </option>
                ))}
              </NativeSelect>
            </div>
          </div>
          <DialogFooter>
            <Button type="submit" disabled={create.isPending}>
              {create.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
              ส่งเรื่อง
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
