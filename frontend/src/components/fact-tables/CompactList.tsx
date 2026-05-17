import { cn } from "@/lib/utils";
import type { ReactNode } from "react";

interface Props<T> {
  items: T[];
  selectedId: number | null;
  onSelect: (id: number) => void;
  getId: (item: T) => number;
  renderRow: (item: T) => ReactNode;
  actions?: (item: T) => ReactNode;
}

export function CompactList<T>({ items, selectedId, onSelect, getId, renderRow, actions }: Props<T>) {
  return (
    <div className="flex-1 overflow-y-auto">
      {items.map((item) => {
        const id = getId(item);
        const selected = id === selectedId;
        return (
          <div
            key={id}
            onClick={() => onSelect(id)}
            className={cn(
              "group flex cursor-pointer items-center gap-2 border-l-2 px-3 py-2 text-sm transition-colors",
              selected ? "border-l-primary bg-primary/5" : "border-l-transparent hover:bg-muted/50",
            )}
          >
            <div className="min-w-0 flex-1">{renderRow(item)}</div>
            {actions && <div className="shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">{actions(item)}</div>}
          </div>
        );
      })}
    </div>
  );
}
