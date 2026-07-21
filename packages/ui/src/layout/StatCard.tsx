import type { ReactNode } from "react";
import { Card } from "../components/ui/card";

export function StatCard({
  label,
  value,
  hint,
  accent,
  bar,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  accent?: "default" | "danger";
  bar?: number;
}) {
  return (
    <Card className="flex-1 p-5">
      <div className="text-[11px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div
        className={
          "mt-2 text-3xl font-semibold leading-none tracking-tight " +
          (accent === "danger" ? "text-rose-400" : "")
        }
      >
        {value}
        {hint ? <span className="ml-2 text-sm font-medium text-muted-foreground">{hint}</span> : null}
      </div>
      {typeof bar === "number" ? (
        <div className="mt-4 h-1.5 overflow-hidden rounded bg-accent">
          <div
            className={"h-full rounded " + (accent === "danger" ? "bg-rose-500" : "bg-emerald-500")}
            style={{ width: `${Math.max(0, Math.min(100, bar))}%` }}
          />
        </div>
      ) : null}
    </Card>
  );
}
