"use client";
import type { SubscriptionStatus } from "@/lib/api/billing";

const COPY: Record<string, string> = {
  none: "You do not have a subscription yet.",
  incomplete: "Your checkout has not completed yet.",
  active: "Your subscription is active.",
  past_due: "Payment failed — update your card to keep hosted ingress running.",
  canceled: "Your subscription has been cancelled and your tenant was removed.",
};

export function SubscriptionCard({
  status,
  onSubscribe,
  onManage,
}: {
  status: SubscriptionStatus | null;
  onSubscribe: () => void;
  onManage: () => void;
}) {
  const state = status?.status ?? "none";
  const hasCustomer = state !== "none";

  return (
    <section className="frame ticks space-y-4 px-6 py-6">
      <div className="briefing-label">subscription</div>
      <p className="font-mono text-xs text-muted-foreground">{COPY[state] ?? state}</p>
      {status?.current_period_end && (
        <p className="stamp text-[11px] text-muted-foreground">
          renews {new Date(status.current_period_end).toLocaleDateString()}
        </p>
      )}
      <div className="flex gap-2">
        <button
          type="button"
          onClick={onSubscribe}
          className="h-10 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
        >
          {state === "active" ? "Change plan" : "Subscribe"}
        </button>
        {hasCustomer && (
          <button
            type="button"
            onClick={onManage}
            className="h-10 rounded-md border border-border px-4 text-sm text-foreground transition-colors hover:bg-accent/30"
          >
            Manage billing
          </button>
        )}
      </div>
    </section>
  );
}
