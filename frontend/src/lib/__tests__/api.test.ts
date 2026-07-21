import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiException, api } from "@/lib/api";

const API_URL = "https://api.saiife.localhost:8000";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

beforeEach(() => {
  document.cookie = "csrf_token=tok-123";
});

afterEach(() => {
  vi.restoreAllMocks();
  document.cookie = "csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
});

describe("api", () => {
  it("sends credentials and the CSRF header", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    await api("/api/v1/auth/me");

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${API_URL}/api/v1/auth/me`);
    expect(init.credentials).toBe("include");
    expect(init.headers["X-CSRF-Token"]).toBe("tok-123");
  });

  it("serialises the json option and sets the content type", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    await api("/api/v1/auth/login", { method: "POST", json: { email: "a@b.co" } });

    const [, init] = fetchMock.mock.calls[0];
    expect(init.headers["Content-Type"]).toBe("application/json");
    expect(init.body).toBe(JSON.stringify({ email: "a@b.co" }));
  });

  it("throws ApiException carrying the backend error code", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({ error: { code: "invalid_credentials", message: "nope" } }, 401),
      ),
    );

    await expect(api("/api/v1/auth/login", { method: "POST" })).rejects.toMatchObject({
      status: 401,
      code: "invalid_credentials",
    });
  });

  it("refreshes once on token_expired then replays the request", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse({ error: { code: "token_expired", message: "expired" } }, 401),
      )
      .mockResolvedValueOnce(jsonResponse({ ok: true }))
      .mockResolvedValueOnce(jsonResponse({ id: "u1" }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await api<{ id: string }>("/api/v1/auth/me");

    expect(result).toEqual({ id: "u1" });
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(fetchMock.mock.calls[1][0]).toBe(`${API_URL}/api/v1/auth/refresh`);
  });

  it("does not retry a 401 that is not a session-expiry code", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        jsonResponse({ error: { code: "invalid_credentials", message: "nope" } }, 401),
      );
    vi.stubGlobal("fetch", fetchMock);

    await expect(api("/api/v1/auth/me")).rejects.toBeInstanceOf(ApiException);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("returns undefined for a 204", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 204 })));
    await expect(api("/api/v1/installs/x", { method: "DELETE" })).resolves.toBeUndefined();
  });
});
