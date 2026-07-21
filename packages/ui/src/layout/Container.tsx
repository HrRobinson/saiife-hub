import type { ReactNode } from "react";
import { cn } from "../cn";

export function Container({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={cn("mx-auto w-full px-[var(--container-pad)]", className)}
      style={{ maxWidth: "var(--container-max)" }}
    >
      {children}
    </div>
  );
}
