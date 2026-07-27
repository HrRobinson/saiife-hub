"use client";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { Toaster, TooltipProvider } from "@saiife/ui";
import { useAuth } from "@/lib/auth-context";

/** Auth gate plus global providers. Page chrome is rendered by AccountShell. */
export default function AuthedLayout({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, loading]);

  if (loading || !user) return null;

  return (
    <TooltipProvider delayDuration={200}>
      {children}
      <Toaster richColors position="bottom-right" />
    </TooltipProvider>
  );
}
