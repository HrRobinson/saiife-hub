import { readCsrfToken } from "./csrf";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "https://api.saiife.localhost:8000";

export type ApiError = { error: { code: string; message: string; details?: unknown } };

export class ApiException extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: unknown,
  ) {
    super(message);
  }
}

let refreshInFlight: Promise<boolean> | null = null;

function csrfHeader(): Record<string, string> {
  const t = readCsrfToken();
  return t ? { "X-CSRF-Token": t } : {};
}

async function refreshOnce(): Promise<boolean> {
  if (!refreshInFlight) {
    refreshInFlight = fetch(`${API_URL}/api/v1/auth/refresh`, {
      method: "POST",
      credentials: "include",
      headers: csrfHeader(),
    })
      .then((r) => r.ok)
      .finally(() => {
        refreshInFlight = null;
      });
  }
  return refreshInFlight;
}

export async function api<T = unknown>(
  path: string,
  init: RequestInit & { json?: unknown } = {},
): Promise<T> {
  const { json, headers, ...rest } = init;
  const opts: RequestInit = {
    credentials: "include",
    ...rest,
    headers: {
      ...(json !== undefined ? { "Content-Type": "application/json" } : {}),
      ...csrfHeader(),
      ...((headers as Record<string, string> | undefined) ?? {}),
    },
    body: json !== undefined ? JSON.stringify(json) : (rest.body as BodyInit | undefined),
  };

  let res = await fetch(`${API_URL}${path}`, opts);
  if (res.status === 401) {
    const body: ApiError | null = await res
      .clone()
      .json()
      .catch(() => null);
    // The access cookie expired (token_expired) or was dropped after its Max-Age
    // (no_session) — the 30-day refresh cookie can still mint a new one.
    const code = body?.error?.code;
    if ((code === "token_expired" || code === "no_session") && (await refreshOnce())) {
      res = await fetch(`${API_URL}${path}`, opts);
    }
  }

  if (!res.ok) {
    const body: ApiError = await res.json().catch(() => ({
      error: { code: "unknown", message: res.statusText },
    }));
    throw new ApiException(res.status, body.error.code, body.error.message, body.error.details);
  }
  if (res.status === 204) return undefined as unknown as T;
  return (await res.json()) as T;
}
