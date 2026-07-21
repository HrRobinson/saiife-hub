import type { HTMLAttributes } from "react";
import { cn } from "./cn";

export function GlassPanel({
  className,
  children,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn("glass-panel relative", className)} {...props}>
      {children}
    </div>
  );
}
