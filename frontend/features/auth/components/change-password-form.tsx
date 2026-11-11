"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";

import { FormField } from "@/components/common/form-field";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { useSetSession } from "@/features/auth/hooks/use-session";
import {
  changePasswordSchema,
  PASSWORD_MIN_LENGTH,
  type ChangePasswordValues,
} from "@/features/auth/schemas";
import { ApiError } from "@/services/api-client";
import { changePassword } from "@/services/auth";

export function ChangePasswordForm() {
  const setSession = useSetSession();
  const form = useForm<ChangePasswordValues>({
    resolver: zodResolver(changePasswordSchema),
    defaultValues: { current: "", password: "", confirm: "" },
  });
  const mutation = useMutation({
    mutationFn: (v: ChangePasswordValues) => changePassword(v.current, v.password),
    onSuccess: (me) => {
      setSession(me);
      form.reset();
      toast.success("เปลี่ยนรหัสผ่านแล้ว อุปกรณ์อื่นทั้งหมดถูกออกจากระบบ");
    },
  });
  const error = mutation.error instanceof ApiError ? mutation.error : null;

  return (
    <form
      noValidate
      className="max-w-md space-y-4"
      onSubmit={form.handleSubmit((v) => mutation.mutate(v))}
    >
      {mutation.isError ? (
        <Alert variant="destructive">
          <AlertDescription>
            {error?.message ?? "เปลี่ยนรหัสผ่านไม่สำเร็จ"}
            {error?.details.length ? `: ${error.details.map((d) => d.message).join(" ")}` : ""}
          </AlertDescription>
        </Alert>
      ) : null}
      <FormField
        label="รหัสผ่านปัจจุบัน"
        type="password"
        autoComplete="current-password"
        registration={form.register("current")}
        error={form.formState.errors.current}
      />
      <FormField
        label="รหัสผ่านใหม่"
        type="password"
        autoComplete="new-password"
        hint={`อย่างน้อย ${PASSWORD_MIN_LENGTH} ตัวอักษร`}
        registration={form.register("password")}
        error={form.formState.errors.password}
      />
      <FormField
        label="ยืนยันรหัสผ่านใหม่"
        type="password"
        autoComplete="new-password"
        registration={form.register("confirm")}
        error={form.formState.errors.confirm}
      />
      <Button type="submit" disabled={mutation.isPending}>
        {mutation.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
        บันทึกรหัสผ่านใหม่
      </Button>
    </form>
  );
}
