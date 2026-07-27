import type { ReactNode } from "react";
import { cn } from "../cn";

export function Section({ children, className }: { children: ReactNode; className?: string }) {
  return <section className={cn("mb-6", className)}>{children}</section>;
}
