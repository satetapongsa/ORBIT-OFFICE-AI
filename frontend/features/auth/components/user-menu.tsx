"use client";

import { useMutation } from "@tanstack/react-query";
import { KeyRound, LogOut } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useSession, useSetSession } from "@/features/auth/hooks/use-session";
import { roleLabel } from "@/features/auth/labels";
import { logout } from "@/services/auth";

function initials(name: string): string {
  const parts = name.trim().split(/\s+/);
  return (parts[0]?.[0] ?? "") + (parts[1]?.[0] ?? "");
}

export function UserMenu() {
  const { me } = useSession();
  const setSession = useSetSession();
  const router = useRouter();
  const signOut = useMutation({
    mutationFn: logout,
    onSettled: () => {
      setSession(null);
      router.replace("/login");
    },
    onSuccess: () => toast.success("ออกจากระบบเรียบร้อยแล้ว"),
  });

  if (!me) return null;
  const { user } = me;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" className="h-10 gap-2 px-2" aria-label="เมนูผู้ใช้">
          <Avatar className="size-8">
            <AvatarFallback className="bg-primary/10 text-primary text-xs font-semibold">
              {initials(user.display_name)}
            </AvatarFallback>
          </Avatar>
          <span className="hidden max-w-40 truncate text-sm font-medium sm:inline">
            {user.display_name}
          </span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-64">
        <DropdownMenuLabel className="space-y-0.5">
          <p className="truncate text-sm font-medium">{user.display_name}</p>
          <p className="text-muted-foreground truncate text-xs font-normal">{user.email}</p>
          <p className="text-muted-foreground text-xs font-normal">
            {user.roles.map((r) => roleLabel(r.code, r.name)).join(" · ")}
            {user.department ? ` · ${user.department.name}` : ""}
          </p>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuGroup>
          <DropdownMenuItem asChild>
            <Link href="/account">
              <KeyRound aria-hidden />
              บัญชีและรหัสผ่าน
            </Link>
          </DropdownMenuItem>
          <DropdownMenuItem
            variant="destructive"
            disabled={signOut.isPending}
            onSelect={(event) => {
              event.preventDefault();
              signOut.mutate();
            }}
          >
            <LogOut aria-hidden />
            ออกจากระบบ
          </DropdownMenuItem>
        </DropdownMenuGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
