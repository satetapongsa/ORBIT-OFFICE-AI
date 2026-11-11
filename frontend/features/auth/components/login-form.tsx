"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { Loader2, LogIn } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useForm } from "react-hook-form";

import { FormField } from "@/components/common/form-field";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { useSetSession } from "@/features/auth/hooks/use-session";
import { loginSchema, type LoginValues } from "@/features/auth/schemas";
import { ApiError } from "@/services/api-client";
import { login, safeRedirectPath } from "@/services/auth";

export function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const setSession = useSetSession();
  const form = useForm<LoginValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "", password: "" },
  });

  const mutation = useMutation({
    mutationFn: (values: LoginValues) => login(values.email, values.password),
    onSuccess: (me) => {
      setSession(me);
      router.replace(safeRedirectPath(params.get("next")));
    },
    onError: () => form.resetField("password"),
  });

  const error = mutation.error instanceof ApiError ? mutation.error : null;

  return (
    <form
      noValidate
      className="space-y-4"
      onSubmit={form.handleSubmit((values) => mutation.mutate(values))}
    >
      {mutation.isError ? (
        <Alert variant="destructive">
          <AlertDescription>
            {error?.message ?? "เข้าสู่ระบบไม่สำเร็จ กรุณาลองใหม่อีกครั้ง"}
          </AlertDescription>
        </Alert>
      ) : null}
      <FormField
        label="อีเมล"
        type="email"
        autoComplete="username"
        autoFocus
        registration={form.register("email")}
        error={form.formState.errors.email}
      />
      <FormField
        label="รหัสผ่าน"
        type="password"
        autoComplete="current-password"
        registration={form.register("password")}
        error={form.formState.errors.password}
      />
      <Button type="submit" className="w-full" disabled={mutation.isPending}>
        {mutation.isPending ? (
          <Loader2 className="animate-spin" aria-hidden />
        ) : (
          <LogIn aria-hidden />
        )}
        เข้าสู่ระบบ
      </Button>
      <p className="text-center text-sm">
        <Link href="/forgot-password" className="text-primary underline-offset-4 hover:underline">
          ลืมรหัสผ่าน?
        </Link>
      </p>
    </form>
  );
}
