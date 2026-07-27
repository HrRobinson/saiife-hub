import { startAuthentication, startRegistration } from "@simplewebauthn/browser";

import { api } from "./api";

type RegistrationOptions = Parameters<typeof startRegistration>[0]["optionsJSON"];
type AuthenticationOptions = Parameters<typeof startAuthentication>[0]["optionsJSON"];

type StartRegistration = { challenge_id: string; options: RegistrationOptions };
type StartAuthentication = { challenge_id: string; options: AuthenticationOptions };

export async function registerPasskey(name: string): Promise<{ id: string; name: string }> {
  const start = await api<StartRegistration>("/api/v1/auth/passkey/register/start", {
    method: "POST",
  });
  const response = await startRegistration({ optionsJSON: start.options });
  return api("/api/v1/auth/passkey/register/finish", {
    method: "POST",
    json: { challenge_id: start.challenge_id, name, response },
  });
}

export async function loginWithPasskey(): Promise<void> {
  const start = await api<StartAuthentication>("/api/v1/auth/passkey/login/start", {
    method: "POST",
  });
  const response = await startAuthentication({ optionsJSON: start.options });
  await api("/api/v1/auth/passkey/login/finish", {
    method: "POST",
    json: { challenge_id: start.challenge_id, response },
  });
}

export type PasskeySummary = {
  id: string;
  name: string;
  created_at: string;
  last_used_at: string | null;
};

export function listPasskeys() {
  return api<PasskeySummary[]>("/api/v1/auth/passkeys");
}

export function renamePasskey(id: string, name: string) {
  return api<{ id: string; name: string }>(`/api/v1/auth/passkeys/${id}`, {
    method: "PATCH",
    json: { name },
  });
}

export function deletePasskey(id: string) {
  return api<void>(`/api/v1/auth/passkeys/${id}`, { method: "DELETE" });
}
