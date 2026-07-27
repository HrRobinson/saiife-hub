"use client";
import { useEffect, useState } from "react";

import { AccountShell } from "@/components/AccountShell";
import { SubscriptionCard } from "@/components/SubscriptionCard";
import { createCheckoutSession, createPortalSession, getSubscription, type SubscriptionStatus } from "@/lib/api/billing";
import { useAuth } from "@/lib/auth-context";

export default function BillingPage() {
  const { user } = useAuth();
  const [status, setStatus] = useState<SubscriptionStatus | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const next = await getSubscription();
      if (!cancelled) setStatus(next);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <AccountShell email={user?.email ?? ""}>
      <div className="briefing-in mb-8">
        <div className="briefing-label">account · billing</div>
        <h1 className="display mt-3 text-2xl text-foreground sm:text-3xl">Billing</h1>
      </div>
      <SubscriptionCard
        status={status}
        onSubscribe={async () => {
          const { url } = await createCheckoutSession();
          window.location.href = url;
        }}
        onManage={async () => {
          const { url } = await createPortalSession();
          window.location.href = url;
        }}
      />
    </AccountShell>
  );
}
