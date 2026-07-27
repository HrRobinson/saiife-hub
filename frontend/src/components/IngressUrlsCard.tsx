"use client";
import { useEffect, useState } from "react";

import { ApiException } from "@/lib/api";
import { listIngressUrls, type IngressUrl } from "@/lib/api/installs";

export function IngressUrlsCard() {
  const [urls, setUrls] = useState<IngressUrl[]>([]);
  const [note, setNote] = useState<string | null>(null);

  useEffect(() => {
    listIngressUrls()
      .then((r) => setUrls(r.ingress_urls))
      .catch((e) => {
        if (e instanceof ApiException && e.code === "cloud_unavailable") {
          setNote("Hosted ingress is not connected yet.");
        } else if (e instanceof ApiException && e.code === "no_tenant") {
          setNote("Subscribe to get your ingress URLs.");
        } else {
          setNote("Could not load your ingress URLs.");
        }
      });
  }, []);

  return (
    <section className="frame ticks space-y-4 px-6 py-6">
      <div className="briefing-label">ingress urls</div>
      {note && <p className="font-mono text-xs text-muted-foreground">{note}</p>}
      {!note && urls.length === 0 && (
        <p className="font-mono text-xs text-muted-foreground">
          No ingress URLs yet — create one from the desktop app.
        </p>
      )}
      {urls.length > 0 && (
        <ul className="divide-y divide-border">
          {urls.map((u) => (
            <li key={u.id} className="py-3">
              <div className="stamp text-[11px] uppercase text-muted-foreground">
                {u.integration}
              </div>
              <code className="mt-1 block break-all font-mono text-xs text-foreground">
                {u.url}
              </code>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
