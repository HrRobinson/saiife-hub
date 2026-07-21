import { api } from "@/lib/api";

export type SubscriptionStatus = {
  status: string;
  current_period_end: string | null;
  has_tenant: boolean;
  account_token_issued_at: string | null;
};

export function getSubscription() {
  return api<SubscriptionStatus>("/api/v1/billing/subscription");
}

export function createCheckoutSession() {
  return api<{ url: string }>("/api/v1/billing/checkout-session", { method: "POST" });
}

export function createPortalSession() {
  return api<{ url: string }>("/api/v1/billing/portal-session", { method: "POST" });
}
