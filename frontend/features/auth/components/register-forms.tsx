"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery } from "@tanstack/react-query";
import { CheckCircle2, Loader2, MailCheck, UserPlus } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useForm } from "react-hook-form";

import { FormField } from "@/components/common/form-field";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useSetSession } from "@/features/auth/hooks/use-session";
import { PASSWORD_MIN_LENGTH, registerSchema, type RegisterValues } from "@/features/auth/schemas";
import { HOME_PATH } from "@/lib/navigation";
import { ApiError } from "@/services/api-client";
import { getRegistrationInfo, register, verifyEmail } from "@/services/auth";

export const registrationQueryKey = ["auth", "registration"] as const;

function errorText(error: unknown, fallback: string): string {
  if (!(error instanceof ApiError)) return fallback;
  const detail = error.details.map((d) => d.message).join(" ");
  return detail ? `${error.message}: ${detail}` : error.message;
}

/** "สมัครสมาชิก" link under the login form, shown only when sign-up is open. */
export function RegisterLink() {
  const info = useQuery({
    queryKey: registrationQueryKey,
    queryFn: ({ signal }) => getRegistrationInfo(signal),
    staleTime: 5 * 60_000,
    retry: false,
  });
  if (!info.data?.enabled) return null;
  return (
    <p className="text-muted-foreground text-center text-sm">
      ยังไม่มีบัญชี?{" "}
      <Link href="/register" className="text-primary underline-offset-4 hover:underline">
        สมัครสมาชิก
      </Link>
    </p>
  );
}

export function RegisterForm() {
  const info = useQuery({
    queryKey: registrationQueryKey,
    queryFn: ({ signal }) => getRegistrationInfo(signal),
    staleTime: 5 * 60_000,
    retry: false,
  });
  const form = useForm<RegisterValues>({
    resolver: zodResolver(registerSchema),
    defaultValues: { first_name: "", last_name: "", email: "", password: "", confirm: "" },
  });
  const mutation = useMutation({
    mutationFn: (v: RegisterValues) =>
      register({
        email: v.email,
        first_name: v.first_name,
        last_name: v.last_name,
        password: v.password,
      }),
    onError: () => {
      form.resetField("password");
      form.resetField("confirm");
    },
  });

  if (info.isPending) return <Skeleton className="h-80 w-full" />;

  if (!info.data?.enabled) {
    return (
      <div className="space-y-4">
        <Alert>
          <AlertDescription>
            ระบบยังไม่เปิดให้สมัครสมาชิกเอง กรุณาติดต่อฝ่ายบุคคลหรือผู้ดูแลระบบเพื่อขอบัญชี
          </AlertDescription>
        </Alert>
        <Button asChild variant="outline" className="w-full">
          <Link href="/login">กลับไปหน้าเข้าสู่ระบบ</Link>
        </Button>
      </div>
    );
  }

  if (mutation.isSuccess) {
    return (
      <div className="space-y-4 text-center">
        <MailCheck className="mx-auto size-10 text-emerald-600" aria-hidden />
        <p className="text-sm">{mutation.data.message}</p>
        <Button asChild variant="outline" className="w-full">
          <Link href="/login">กลับไปหน้าเข้าสู่ระบบ</Link>
        </Button>
      </div>
    );
  }

  const domains = info.data.allowed_domains.map((d) => `@${d}`).join(", ");

  return (
    <form noValidate className="space-y-4" onSubmit={form.handleSubmit((v) => mutation.mutate(v))}>
      {mutation.isError ? (
        <Alert variant="destructive">
          <AlertDescription>
            {errorText(mutation.error, "สมัครสมาชิกไม่สำเร็จ กรุณาลองใหม่")}
          </AlertDescription>
        </Alert>
      ) : null}
      <div className="grid gap-4 sm:grid-cols-2">
        <FormField
          label="ชื่อ"
          autoComplete="given-name"
          autoFocus
          registration={form.register("first_name")}
          error={form.formState.errors.first_name}
        />
        <FormField
          label="นามสกุล"
          autoComplete="family-name"
          registration={form.register("last_name")}
          error={form.formState.errors.last_name}
        />
      </div>
      <FormField
        label="อีเมลบริษัท"
        type="email"
        autoComplete="email"
        hint={`ใช้ได้เฉพาะอีเมล ${domains}`}
        registration={form.register("email")}
        error={form.formState.errors.email}
      />
      <FormField
        label="รหัสผ่าน"
        type="password"
        autoComplete="new-password"
        hint={`อย่างน้อย ${PASSWORD_MIN_LENGTH} ตัวอักษร และไม่ควรเดาง่าย`}
        registration={form.register("password")}
        error={form.formState.errors.password}
      />
      <FormField
        label="ยืนยันรหัสผ่าน"
        type="password"
        autoComplete="new-password"
        registration={form.register("confirm")}
        error={form.formState.errors.confirm}
      />
      <Button type="submit" className="w-full" disabled={mutation.isPending}>
        {mutation.isPending ? (
          <Loader2 className="animate-spin" aria-hidden />
        ) : (
          <UserPlus aria-hidden />
        )}
        สมัครสมาชิก
      </Button>
      <p className="text-muted-foreground text-center text-sm">
        มีบัญชีอยู่แล้ว?{" "}
        <Link href="/login" className="text-primary underline-offset-4 hover:underline">
          เข้าสู่ระบบ
        </Link>
      </p>
    </form>
  );
}

/**
 * Confirms the address from the e-mailed link. The user presses a button (instead of the page
 * confirming on load) so that mail scanners that open links cannot use up the single-use token.
 */
export function VerifyEmailForm() {
  const token = useSearchParams().get("token") ?? "";
  const router = useRouter();
  const setSession = useSetSession();
  const mutation = useMutation({
    mutationFn: () => verifyEmail(token),
    onSuccess: (me) => {
      setSession(me);
      router.replace(HOME_PATH);
    },
  });

  if (!token) {
    return (
      <Alert variant="destructive">
        <AlertDescription>ลิงก์ไม่ถูกต้อง กรุณาสมัครสมาชิกใหม่อีกครั้ง</AlertDescription>
      </Alert>
    );
  }

  if (mutation.isSuccess) {
    return (
      <div className="space-y-4 text-center">
        <CheckCircle2 className="mx-auto size-10 text-emerald-600" aria-hidden />
        <p className="text-sm">ยืนยันอีเมลเรียบร้อย กำลังพาไปหน้าแรก…</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {mutation.isError ? (
        <Alert variant="destructive">
          <AlertDescription>{errorText(mutation.error, "ยืนยันอีเมลไม่สำเร็จ")}</AlertDescription>
        </Alert>
      ) : null}
      <Button className="w-full" disabled={mutation.isPending} onClick={() => mutation.mutate()}>
        {mutation.isPending ? (
          <Loader2 className="animate-spin" aria-hidden />
        ) : (
          <MailCheck aria-hidden />
        )}
        ยืนยันอีเมลและเปิดใช้งานบัญชี
      </Button>
      {mutation.isError ? (
        <Button asChild variant="outline" className="w-full">
          <Link href="/register">สมัครใหม่อีกครั้ง</Link>
        </Button>
      ) : null}
    </div>
  );
}
