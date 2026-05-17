import type { ReactNode } from "react";

export function MasterDetailLayout({ master, detail }: { master: ReactNode; detail: ReactNode }) {
  return (
    <div className="flex h-full gap-px rounded-lg border bg-border">
      <div className="flex w-[40%] min-w-0 flex-col bg-card">{master}</div>
      <div className="flex flex-1 flex-col bg-card">{detail}</div>
    </div>
  );
}
