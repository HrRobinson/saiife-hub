"use client";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useAuth } from "@/lib/auth-context";

export default function OAuthCallback() {
  const router = useRouter();
  const { refresh } = useAuth();
  useEffect(() => {
    void refresh().then(() => router.replace("/dashboard"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return (
    <div className="frame ticks w-full max-w-sm px-6 py-10 text-center">
      <div className="briefing-label mx-auto w-fit">oauth</div>
      <p className="stamp mt-6 text-xs text-muted-foreground">finishing sign-in…</p>
    </div>
  );
}
