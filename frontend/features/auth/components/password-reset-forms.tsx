"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { CheckCircle2, Loader2 } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useForm } from "react-hook-form";

import { FormField } from "@/components/common/form-field";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  forgotPasswordSchema,
  PASSWORD_MIN_LENGTH,
  resetPasswordSchema,
  type ForgotPasswordValues,
  type ResetPasswordValues,
} from "@/features/auth/schemas";
import { ApiError } from "@/services/api-client";
import { confirmPasswordReset, requestPasswordReset } from "@/services/auth";

function errorText(error: unknown, fallback: string): string {
  if (!(error instanceof ApiError)) return fallback;
  const detail = error.details.map((d) => d.message).join(" ");
  return detail ? `${error.message}: ${detail}` : error.message;
}

export function ForgotPasswordForm() {
  const form = useForm<ForgotPasswordValues>({
    resolver: zodResolver(forgotPasswordSchema),
    defaultValues: { email: "" },
  });
  const mutation = useMutation({
    mutationFn: (v: ForgotPasswordValues) => requestPasswordReset(v.email),
  });

  if (mutation.isSuccess) {
    return (
      <div className="space-y-4 text-center">
        <CheckCircle2 className="mx-auto size-10 text-emerald-600" aria-hidden />
        <p className="text-sm">{mutation.data.message}</p>
        <Button asChild variant="outline" className="w-full">
          <Link href="/login">กลับไปหน้าเข้าสู่ระบบ</Link>
        </Button>
      </div>
    );
  }

  return (
    <form noValidate className="space-y-4" onSubmit={form.handleSubmit((v) => mutation.mutate(v))}>
      {mutation.isError ? (
        <Alert variant="destructive">
          <AlertDescription>
            {errorText(mutation.error, "ส่งคำขอไม่สำเร็จ กรุณาลองใหม่")}
          </AlertDescription>
        </Alert>
      ) : null}
      <FormField
        label="อีเมลที่ใช้เข้าสู่ระบบ"
        type="email"
        autoComplete="email"
        autoFocus
        registration={form.register("email")}
        error={form.formState.errors.email}
      />
      <Button type="submit" className="w-full" disabled={mutation.isPending}>
        {mutation.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
        ส่งลิงก์ตั้งรหัสผ่านใหม่
      </Button>
      <p className="text-center text-sm">
        <Link href="/login" className="text-primary underline-offset-4 hover:underline">
          กลับไปหน้าเข้าสู่ระบบ
        </Link>
      </p>
    </form>
  );
}

export function ResetPasswordForm() {
  const token = useSearchParams().get("token") ?? "";
  const form = useForm<ResetPasswordValues>({
    resolver: zodResolver(resetPasswordSchema),
    defaultValues: { password: "", confirm: "" },
  });
  const mutation = useMutation({
    mutationFn: (v: ResetPasswordValues) => confirmPasswordReset(token, v.password),
  });

  if (!token) {
    return (
      <Alert variant="destructive">
        <AlertDescription>ลิงก์ไม่ถูกต้อง กรุณาขอลิงก์ตั้งรหัสผ่านใหม่อีกครั้ง</AlertDescription>
      </Alert>
    );
  }

  if (mutation.isSuccess) {
    return (
      <div className="space-y-4 text-center">
        <CheckCircle2 className="mx-auto size-10 text-emerald-600" aria-hidden />
        <p className="text-sm">{mutation.data.message}</p>
        <Button asChild className="w-full">
          <Link href="/login">ไปหน้าเข้าสู่ระบบ</Link>
        </Button>
      </div>
    );
  }

  return (
    <form noValidate className="space-y-4" onSubmit={form.handleSubmit((v) => mutation.mutate(v))}>
      {mutation.isError ? (
        <Alert variant="destructive">
          <AlertDescription>{errorText(mutation.error, "ตั้งรหัสผ่านไม่สำเร็จ")}</AlertDescription>
        </Alert>
      ) : null}
      <FormField
        label="รหัสผ่านใหม่"
        type="password"
        autoComplete="new-password"
        autoFocus
        hint={`อย่างน้อย ${PASSWORD_MIN_LENGTH} ตัวอักษร และไม่ควรเดาง่าย`}
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
      <Button type="submit" className="w-full" disabled={mutation.isPending}>
        {mutation.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
        ตั้งรหัสผ่านใหม่
      </Button>
    </form>
  );
}
