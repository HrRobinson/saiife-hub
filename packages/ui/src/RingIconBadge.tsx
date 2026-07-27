import type { ReactNode } from "react";
import { cn } from "./cn";

export function RingIconBadge({
  children,
  active = false,
  className,
}: {
  children: ReactNode;
  active?: boolean;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex h-12 w-12 items-center justify-center rounded-full transition-all duration-300",
        active
          ? "brand-gradient text-primary-foreground glow-ring"
          : "border border-border text-muted-foreground bg-card/30",
        className,
      )}
    >
      {children}
    </span>
  );
}
