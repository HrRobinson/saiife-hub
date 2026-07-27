"use client";
import { useCallback, useEffect, useState } from "react";

import { Input } from "@saiife/ui";
import { createInstall, deleteInstall, listInstalls, type Install } from "@/lib/api/installs";

export function InstallsCard() {
  const [installs, setInstalls] = useState<Install[] | null>(null);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);

  const reload = useCallback(async () => {
    setInstalls(await listInstalls());
  }, []);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const next = await listInstalls();
      if (!cancelled) setInstalls(next);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  async function add() {
    if (!name.trim()) return;
    setBusy(true);
    try {
      await createInstall(name.trim());
      setName("");
      await reload();
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: string) {
    setBusy(true);
    try {
      await deleteInstall(id);
      await reload();
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="frame ticks space-y-4 px-6 py-6">
      <div className="briefing-label">connected installs</div>

      {installs !== null && installs.length === 0 && (
        <p className="font-mono text-xs text-muted-foreground">No installs linked yet.</p>
      )}

      {installs !== null && installs.length > 0 && (
        <ul className="divide-y divide-border">
          {installs.map((i) => (
            <li key={i.id} className="flex items-center justify-between py-3">
              <div className="min-w-0">
                <div className="truncate text-sm text-foreground">{i.name}</div>
                <div className="stamp text-[11px] text-muted-foreground">
                  linked {new Date(i.created_at).toLocaleDateString()}
                </div>
              </div>
              <button
                type="button"
                aria-label={`Remove ${i.name}`}
                disabled={busy}
                onClick={() => void remove(i.id)}
                className="stamp rounded border border-border px-2 py-1 text-[10px] uppercase text-muted-foreground hover:border-rose-500/60 hover:text-rose-400 disabled:opacity-50"
              >
                remove
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="flex items-end gap-2">
        <div className="flex-1">
          <label className="briefing-label" htmlFor="install-name">
            install name
          </label>
          <Input
            id="install-name"
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
          className="h-10 rounded-md border border-border px-4 text-sm text-foreground transition-colors hover:bg-accent/30 disabled:opacity-50"
        >
          Link install
        </button>
      </div>
    </section>
  );
}
