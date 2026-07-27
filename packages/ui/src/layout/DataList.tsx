import type { ReactNode } from "react";
import { Card } from "../components/ui/card";

export function DataList({ header, children }: { header?: ReactNode; children: ReactNode }) {
  return (
    <Card className="overflow-hidden p-0">
      {header ? (
        <div className="flex items-center justify-between border-b border-border px-4 py-3 text-sm font-semibold">
          {header}
        </div>
      ) : null}
      <div className="divide-y divide-border">{children}</div>
    </Card>
  );
}

export function DataRow({ children }: { children: ReactNode }) {
  return <div className="flex items-center justify-between px-4 py-3 text-sm">{children}</div>;
}
