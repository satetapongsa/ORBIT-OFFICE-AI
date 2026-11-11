/** Thai labels for audit actions shown in activity feeds (unknown actions show their code). */
const ACTION_LABELS: Record<string, string> = {
  "auth.login": "เข้าสู่ระบบ",
  "auth.login_failed": "เข้าสู่ระบบไม่สำเร็จ",
  "auth.login_rate_limited": "ถูกจำกัดการเข้าสู่ระบบชั่วคราว",
  "auth.logout": "ออกจากระบบ",
  "auth.refresh_reuse_detected": "ตรวจพบการใช้เซสชันซ้ำ",
  "auth.password_changed": "เปลี่ยนรหัสผ่าน",
  "auth.password_reset_requested": "ขอรีเซ็ตรหัสผ่าน",
  "auth.password_reset_completed": "รีเซ็ตรหัสผ่านสำเร็จ",
  "user.created": "สร้างบัญชีผู้ใช้",
  "user.updated": "แก้ไขข้อมูลผู้ใช้",
  "user.deactivated": "ระงับบัญชีผู้ใช้",
  "user.activated": "เปิดใช้งานบัญชีผู้ใช้",
  "user.roles_changed": "เปลี่ยนบทบาทผู้ใช้",
  "role.created": "สร้างบทบาท",
  "role.updated": "แก้ไขบทบาท",
  "role.deleted": "ลบบทบาท",
  "role.permissions_changed": "เปลี่ยนสิทธิ์ของบทบาท",
  "department.created": "สร้างแผนก",
  "department.updated": "แก้ไขแผนก",
  "department.deleted": "ลบแผนก",
};

/** Actions that deserve attention in a security feed. */
const WARNING_ACTIONS = new Set([
  "auth.login_failed",
  "auth.login_rate_limited",
  "auth.refresh_reuse_detected",
]);

export function actionLabel(action: string): string {
  return ACTION_LABELS[action] ?? action;
}

export function isWarningAction(action: string): boolean {
  return WARNING_ACTIONS.has(action);
}
