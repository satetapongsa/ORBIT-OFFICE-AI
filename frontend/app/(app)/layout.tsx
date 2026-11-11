import { AppShell } from "@/components/layout/app-shell";
import { AuthGate } from "@/features/auth/components/auth-gate";

// Everything under (app) renders only after the client-side session check (AuthGate),
// so its segments are not prerendered; opt out of instant-navigation validation.
export const instant = false;

export default function AppLayout({ children }: LayoutProps<"/">) {
  return (
    <AuthGate>
      <AppShell>{children}</AppShell>
    </AuthGate>
  );
}
