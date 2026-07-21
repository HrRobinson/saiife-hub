import type { ReactNode } from "react";
import { cn } from "./cn";

export function Eyebrow({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "font-mono text-xs uppercase tracking-[0.18em] text-primary/80",
        className,
      )}
    >
      {children}
    </span>
  );
}
