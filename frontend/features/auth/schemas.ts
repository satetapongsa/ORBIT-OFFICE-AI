import { z } from "zod";

/** Client-side checks mirror the backend policy; the backend remains the authority. */
export const PASSWORD_MIN_LENGTH = 12;

const email = z
  .string()
  .trim()
  .min(1, "กรุณากรอกอีเมล")
  .email("รูปแบบอีเมลไม่ถูกต้อง")
  .max(320, "อีเมลยาวเกินไป");

const newPassword = z
  .string()
  .min(PASSWORD_MIN_LENGTH, `รหัสผ่านต้องมีอย่างน้อย ${PASSWORD_MIN_LENGTH} ตัวอักษร`)
  .max(256, "รหัสผ่านยาวเกินไป");

export const loginSchema = z.object({
  email,
  password: z.string().min(1, "กรุณากรอกรหัสผ่าน").max(256, "รหัสผ่านยาวเกินไป"),
});

export const forgotPasswordSchema = z.object({ email });

export const resetPasswordSchema = z
  .object({ password: newPassword, confirm: z.string() })
  .refine((v) => v.password === v.confirm, {
    message: "รหัสผ่านทั้งสองช่องไม่ตรงกัน",
    path: ["confirm"],
  });

export const changePasswordSchema = z
  .object({
    current: z.string().min(1, "กรุณากรอกรหัสผ่านปัจจุบัน"),
    password: newPassword,
    confirm: z.string(),
  })
  .refine((v) => v.password === v.confirm, {
    message: "รหัสผ่านทั้งสองช่องไม่ตรงกัน",
    path: ["confirm"],
  })
  .refine((v) => v.password !== v.current, {
    message: "รหัสผ่านใหม่ต้องไม่ซ้ำกับรหัสผ่านเดิม",
    path: ["password"],
  });

export type LoginValues = z.infer<typeof loginSchema>;
export type ForgotPasswordValues = z.infer<typeof forgotPasswordSchema>;
export type ResetPasswordValues = z.infer<typeof resetPasswordSchema>;
export type ChangePasswordValues = z.infer<typeof changePasswordSchema>;
