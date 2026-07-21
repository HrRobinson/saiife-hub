"use client";
import { useCallback, useEffect, useState } from "react";

import { Input } from "@saiife/ui";
import {
  deletePasskey,
  listPasskeys,
  registerPasskey,
  type PasskeySummary,
} from "@/lib/passkey";

export function PasskeyList() {
  const [passkeys, setPasskeys] = useState<PasskeySummary[] | null>(null);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      setPasskeys(await listPasskeys());
    } catch {
      setError("Could not load your passkeys.");
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  async function add() {
    setError(null);
    setBusy(true);
    try {
      await registerPasskey(name || "Unnamed passkey");
      setName("");
      await reload();
    } catch {
      setError("Passkey registration was cancelled or failed.");
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: string) {
    setError(null);
    setBusy(true);
    try {
      await deletePasskey(id);
      await reload();
    } catch {
      setError("Could not remove that passkey.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="frame ticks space-y-5 px-6 py-6">
      <div className="briefing-label">passkeys</div>

      {passkeys === null && <p className="stamp text-xs text-muted-foreground">loading…</p>}

      {passkeys !== null && passkeys.length === 0 && (
        <p className="font-mono text-xs text-muted-foreground">
          No passkeys registered yet. Add one to sign in without a password.
        </p>
      )}

      {passkeys !== null && passkeys.length > 0 && (
        <ul className="divide-y divide-border">
          {passkeys.map((p) => (
            <li key={p.id} className="flex items-center justify-between py-3">
              <div className="min-w-0">
                <div className="truncate text-sm text-foreground">{p.name}</div>
                <div className="stamp text-[11px] text-muted-foreground">
                  added {new Date(p.created_at).toLocaleDateString()}
                  {p.last_used_at
                    ? ` · last used ${new Date(p.last_used_at).toLocaleDateString()}`
                    : " · never used"}
                </div>
              </div>
              <button
                type="button"
                aria-label={`Remove ${p.name}`}
                disabled={busy}
                onClick={() => void remove(p.id)}
                className="stamp rounded border border-border px-2 py-1 text-[10px] uppercase text-muted-foreground transition-colors hover:border-rose-500/60 hover:text-rose-400 disabled:opacity-50"
              >
                remove
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="flex items-end gap-2">
        <div className="flex-1">
          <label className="briefing-label" htmlFor="pk-name">
            passkey name
          </label>
          <Input
            id="pk-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Work laptop"
            className="mt-2 h-10 font-mono"
          />
        </div>
        <button
          type="button"
          disabled={busy}
          onClick={() => void add()}
          className="h-10 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-60"
        >
          Add passkey
        </button>
      </div>

      {error && (
        <p className="border-l-2 border-rose-500 pl-3 font-mono text-[11px] text-rose-400">
          {error}
        </p>
      )}
    </section>
  );
}
