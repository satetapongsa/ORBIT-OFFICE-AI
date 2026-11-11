import { Brand } from "@/components/layout/brand";

export default function AuthLayout({ children }: LayoutProps<"/">) {
  return (
    <main className="from-primary/5 via-background to-background flex min-h-screen items-center justify-center bg-gradient-to-b px-4 py-12">
      <div className="w-full max-w-sm space-y-6">
        <div className="flex justify-center">
          <Brand />
        </div>
        {children}
      </div>
    </main>
  );
}
