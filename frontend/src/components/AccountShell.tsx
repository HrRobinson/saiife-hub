"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import type { ReactNode } from "react";

import {
  Avatar,
  AvatarFallback,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@saiife/ui";
import { useAuth } from "@/lib/auth-context";

/** Slim console chrome: brand on the left, account menu on the right. */
export function AccountShell({ email, children }: { email: string; children: ReactNode }) {
  const { resolvedTheme, setTheme } = useTheme();
  const router = useRouter();
  const { logout } = useAuth();
  const initials = email.slice(0, 2).toUpperCase();

  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex h-11 items-center justify-between border-b border-border px-4 sm:px-6">
        <div className="flex items-center gap-5">
          <span className="display text-[15px] text-foreground">saiife</span>
          <nav className="flex items-center gap-4">
            <Link href="/dashboard" className="stamp text-xs text-muted-foreground hover:text-foreground">
              dashboard
            </Link>
            <Link href="/billing" className="stamp text-xs text-muted-foreground hover:text-foreground">
              billing
            </Link>
            <Link
              href="/settings/security"
              className="stamp text-xs text-muted-foreground hover:text-foreground"
            >
              security
            </Link>
          </nav>
        </div>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              className="flex min-w-0 items-center gap-2 rounded-sm border border-border px-2 py-1 transition-colors hover:bg-accent/30"
              aria-label="User menu"
            >
              <Avatar className="h-5 w-5 shrink-0 rounded-sm">
                <AvatarFallback className="rounded-sm bg-card font-mono text-[9px] text-muted-foreground">
                  {initials}
                </AvatarFallback>
              </Avatar>
              <span className="stamp hidden max-w-[160px] truncate text-xs text-muted-foreground sm:inline">
                {email}
              </span>
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent side="bottom" align="end" className="w-56">
            <DropdownMenuLabel className="stamp text-xs text-muted-foreground">
              {email}
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}>
              {resolvedTheme === "dark" ? "Switch to light" : "Switch to dark"}
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onClick={async () => {
                try {
                  await logout();
                } catch {
                  /* the cookies are cleared server-side either way */
                }
                router.push("/login");
              }}
            >
              Sign out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </header>

      <main className="flex-1 px-4 py-6 sm:px-6 sm:py-8">
        <div className="mx-auto min-w-0 max-w-3xl">{children}</div>
      </main>
    </div>
  );
}
