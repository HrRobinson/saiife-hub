import type { ReactNode } from "react";
import { cn } from "./cn";

export type Status = "ok" | "warn" | "fail" | "neutral";

const DOT: Record<Status, string> = {
  ok: "bg-success",
  warn: "bg-warning",
  fail: "bg-destructive",
  neutral: "bg-muted-foreground",
};

export function StatusDot({
  status,
  children,
  className,
}: {
  status: Status;
  children?: ReactNode;
  className?: string;
}) {
  return (
    <span className={cn("inline-flex items-center gap-2 text-sm", className)}>
      <span className={cn("h-2 w-2 rounded-full", DOT[status])} aria-hidden />
      {children}
    </span>
  );
}
