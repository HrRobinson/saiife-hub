"use client";
import { useCallback, useEffect, useState } from "react";

import { AccountShell } from "@/components/AccountShell";
import { AccountTokenCard } from "@/components/AccountTokenCard";
import { DeliveryHistoryCard } from "@/components/DeliveryHistoryCard";
import { IngressUrlsCard } from "@/components/IngressUrlsCard";
import { InstallsCard } from "@/components/InstallsCard";
import { SubscriptionCard } from "@/components/SubscriptionCard";
import { createCheckoutSession, createPortalSession, getSubscription, type SubscriptionStatus } from "@/lib/api/billing";
import { useAuth } from "@/lib/auth-context";

const ENTITLED = new Set(["active", "trialing", "past_due"]);

export default function DashboardPage() {
  const { user } = useAuth();
  const [status, setStatus] = useState<SubscriptionStatus | null>(null);

  const reload = useCallback(async () => {
    setStatus(await getSubscription());
  }, []);

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
        <div className="briefing-label">hosted ingress</div>
        <h1 className="display mt-3 text-2xl text-foreground sm:text-3xl">Dashboard</h1>
      </div>

      <div className="space-y-6">
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
        <AccountTokenCard
          entitled={ENTITLED.has(status?.status ?? "none")}
          issuedAt={status?.account_token_issued_at ?? null}
          onIssued={() => void reload()}
        />
        <InstallsCard />
        <IngressUrlsCard />
        <DeliveryHistoryCard />
      </div>
    </AccountShell>
  );
}
