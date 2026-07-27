"use client";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { ApiException, api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";

function VerifyEmailInner() {
  const params = useSearchParams();
  const router = useRouter();
  const { refresh } = useAuth();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const token = params.get("token");
    if (!token) {
      setError("This verification link is missing its token.");
      return;
    }
    api("/api/v1/auth/verify-email", { method: "POST", json: { token } })
      .then(async () => {
        await refresh();
        router.replace("/dashboard");
      })
      .catch((e) =>
        setError(e instanceof ApiException ? e.message : "Verification failed."),
      );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (error) {
    return (
      <p className="border-l-2 border-rose-500 pl-3 font-mono text-[11px] text-rose-400">
        {error}
      </p>
    );
  }
  return <p className="stamp text-xs text-muted-foreground">verifying…</p>;
}

export default function VerifyEmailPage() {
  return (
    <div className="frame ticks w-full max-w-sm px-6 py-10 text-center">
      <div className="briefing-label mx-auto w-fit">email verification</div>
      <div className="mt-6 flex justify-center">
        <Suspense fallback={<p className="stamp text-xs text-muted-foreground">verifying…</p>}>
          <VerifyEmailInner />
        </Suspense>
      </div>
    </div>
  );
}
