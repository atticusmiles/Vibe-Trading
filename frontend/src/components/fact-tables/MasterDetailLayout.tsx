import type { ReactNode } from "react";

export function MasterDetailLayout({ master, detail }: { master: ReactNode; detail: ReactNode }) {
  return (
    <div className="flex h-full gap-px rounded-lg border bg-border overflow-hidden">
      <div className="flex w-[40%] min-w-0 flex-col bg-card overflow-hidden">{master}</div>
      <div className="flex min-w-0 flex-1 flex-col bg-card overflow-hidden">{detail}</div>
    </div>
  );
}
