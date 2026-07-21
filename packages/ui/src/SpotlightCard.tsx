"use client";

import {
  type CSSProperties,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from "react";
import { cn } from "./cn";

function track(e: ReactPointerEvent<HTMLDivElement>) {
  const el = e.currentTarget;
  const r = el.getBoundingClientRect();
  el.style.setProperty("--mx", `${((e.clientX - r.left) / r.width) * 100}%`);
  el.style.setProperty("--my", `${((e.clientY - r.top) / r.height) * 100}%`);
}

export function SpotlightCard({
  children,
  active = false,
  className,
}: {
  children: ReactNode;
  active?: boolean;
  className?: string;
}) {
  return (
    <div
      onPointerMove={track}
      style={{ "--mx": "50%", "--my": "40%" } as CSSProperties}
      className={cn(
        "group relative overflow-hidden rounded-[var(--radius)] border border-border p-6 transition-colors duration-300",
        "hover:border-[var(--border-glow)]",
        active && "border-[var(--border-glow)]",
        className,
      )}
    >
      {/* Cursor-tracking spotlight — the glow pools under the pointer. */}
      <div
        aria-hidden
        className={cn(
          "pointer-events-none absolute inset-0 opacity-0 transition-opacity duration-300",
          "group-hover:opacity-100 motion-reduce:transition-none",
          active && "opacity-100",
        )}
        style={{
          backgroundImage:
            "radial-gradient(circle at var(--mx) var(--my), color-mix(in oklch, var(--brand-from) 30%, transparent), color-mix(in oklch, var(--brand-to) 12%, transparent) 34%, transparent 60%)",
        }}
      />
      <div className="relative z-10">{children}</div>
    </div>
  );
}
