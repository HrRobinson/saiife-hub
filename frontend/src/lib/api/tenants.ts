import { api } from "@/lib/api";

export type TenantSummary = {
  cloud_tenant_id: string;
  tenant_lookup_id: string;
  account_token_issued_at: string | null;
};

export type IssuedToken = {
  token: string;
  cloud_tenant_id: string;
  issued_at: string;
};

export function getTenant() {
  return api<TenantSummary>("/api/v1/tenants/me");
}

/** Returns the plaintext token EXACTLY ONCE. Never persist it client-side. */
export function issueAccountToken() {
  return api<IssuedToken>("/api/v1/tenants/account-token", { method: "POST" });
}
