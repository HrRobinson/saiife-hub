"use client";
import { useState } from "react";

import { issueAccountToken } from "@/lib/api/tenants";

export function AccountTokenCard({
  entitled,
  issuedAt,
  onIssued,
}: {
  entitled: boolean;
  issuedAt: string | null;
  onIssued: () => void;
}) {
  const [token, setToken] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const label = issuedAt ? "Rotate account token" : "Issue account token";

  async function issue() {
    setError(null);
    setBusy(true);
    try {
      const issued = await issueAccountToken();
      setToken(issued.token);
      onIssued();
    } catch {
      setError("Could not issue a token — try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="frame ticks space-y-4 px-6 py-6">
      <div className="briefing-label">account token</div>

      {/* Deliberately avoids the phrase "shown once" — that string belongs to the
          reveal box below, so a test can assert on it unambiguously. */}
      <p className="font-mono text-xs leading-relaxed text-muted-foreground">
        Paste this into the saiife desktop app to connect it to hosted ingress. The secret is{" "}
        <span className="text-foreground/80">revealed a single time</span> and never stored — we
        keep only a hash.
      </p>

      {!entitled && (
        <p className="font-mono text-[11px] text-muted-foreground">
          An active subscription is required to issue an account token.
        </p>
      )}

      {issuedAt && (
        <p className="stamp text-[11px] text-muted-foreground">
          last issued {new Date(issuedAt).toLocaleString()} · rotating invalidates the previous
          token immediately
        </p>
      )}

      {token && (
        <div className="space-y-3 rounded-md border border-[var(--border-glow)] bg-card/40 p-4">
          <div className="briefing-label">shown once — copy it now</div>
          <code className="block break-all font-mono text-xs text-foreground">{token}</code>
          <button
            type="button"
            onClick={() => setToken(null)}
            className="stamp rounded border border-border px-2 py-1 text-[10px] uppercase text-muted-foreground hover:text-foreground"
          >
            I saved it
          </button>
        </div>
      )}

      <button
        type="button"
        disabled={!entitled || busy}
        onClick={() => void issue()}
        className="h-10 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
      >
        {busy ? "Working…" : label}
      </button>

      {error && (
        <p className="border-l-2 border-rose-500 pl-3 font-mono text-[11px] text-rose-400">
          {error}
        </p>
      )}
    </section>
  );
}
