"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmailPreferencesCard } from "@/features/account/components/email-preferences-card";
import { ChangePasswordForm } from "@/features/auth/components/change-password-form";
import { useSession } from "@/features/auth/hooks/use-session";
import { roleLabel } from "@/features/auth/labels";

const dateTime = new Intl.DateTimeFormat("th-TH", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "Asia/Bangkok",
});

export function AccountOverview() {
  const { me } = useSession();
  if (!me) return null;
  const { user } = me;
  const rows: [string, string][] = [
    ["ชื่อที่แสดง", user.display_name],
    ["อีเมล", user.email],
    ["รหัสพนักงาน", user.employee_code],
    ["แผนก", user.department?.name ?? "—"],
    ["ตำแหน่ง", user.job_title ?? "—"],
    ["เข้าสู่ระบบล่าสุด", user.last_login_at ? dateTime.format(new Date(user.last_login_at)) : "—"],
  ];

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>ข้อมูลบัญชี</CardTitle>
          <CardDescription>หากข้อมูลไม่ถูกต้อง กรุณาติดต่อฝ่ายบุคคล</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <dl className="grid grid-cols-[8rem_1fr] gap-x-4 gap-y-2 text-sm">
            {rows.map(([label, value]) => (
              <div key={label} className="contents">
                <dt className="text-muted-foreground">{label}</dt>
                <dd className="break-all">{value}</dd>
              </div>
            ))}
          </dl>
          <div className="flex flex-wrap gap-1.5" aria-label="บทบาท">
            {user.roles.map((role) => (
              <Badge key={role.id} variant="secondary">
                {roleLabel(role.code, role.name)}
              </Badge>
            ))}
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>เปลี่ยนรหัสผ่าน</CardTitle>
          <CardDescription>
            เมื่อเปลี่ยนแล้ว อุปกรณ์อื่นที่เข้าสู่ระบบอยู่จะถูกออกจากระบบ
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ChangePasswordForm />
        </CardContent>
      </Card>
      <EmailPreferencesCard />
    </div>
  );
}
