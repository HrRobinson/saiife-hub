"use client";
import { useEffect, useState } from "react";

import { ApiException } from "@/lib/api";
import { listDeliveries, type Delivery } from "@/lib/api/installs";

export function DeliveryHistoryCard() {
  const [deliveries, setDeliveries] = useState<Delivery[]>([]);
  const [note, setNote] = useState<string | null>(null);

  useEffect(() => {
    listDeliveries(20)
      .then((r) => setDeliveries(r.deliveries))
      .catch((e) => {
        if (e instanceof ApiException && (e.code === "cloud_unavailable" || e.code === "no_tenant")) {
          setNote("Delivery history will appear once hosted ingress is connected.");
        } else {
          setNote("Could not load delivery history.");
        }
      });
  }, []);

  return (
    <section className="frame ticks space-y-4 px-6 py-6">
      <div className="briefing-label">recent deliveries</div>
      {note && <p className="font-mono text-xs text-muted-foreground">{note}</p>}
      {!note && deliveries.length === 0 && (
        <p className="font-mono text-xs text-muted-foreground">No deliveries yet.</p>
      )}
      {deliveries.length > 0 && (
        <ul className="divide-y divide-border">
          {deliveries.map((d) => (
            <li key={d.delivery_id} className="flex items-center justify-between py-2">
              <div className="min-w-0">
                <div className="stamp text-[11px] uppercase text-muted-foreground">
                  {d.integration} · {d.status}
                </div>
                <code className="block truncate font-mono text-[11px] text-foreground/70">
                  {d.delivery_id}
                </code>
              </div>
              <span className="stamp shrink-0 text-[11px] text-muted-foreground">
                {new Date(d.received_at).toLocaleTimeString()}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
