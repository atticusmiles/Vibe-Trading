import { cn } from "@/lib/utils";

const FILTERS = [
  { key: null, label: "全部" },
  { key: "active", label: "活跃" },
  { key: "proposed", label: "提议中" },
  { key: "adopted", label: "已采纳" },
  { key: "rejected", label: "已否决" },
  { key: "removed", label: "已移除" },
];

export function StatusFilterBar({ active, onChange }: { active: string | null; onChange: (s: string | null) => void }) {
  return (
    <div className="flex flex-wrap gap-1">
      {FILTERS.map((f) => (
        <button
          key={f.label}
          onClick={() => onChange(f.key)}
          className={cn(
            "rounded-full px-2.5 py-0.5 text-xs font-medium transition",
            active === f.key ? "bg-primary/10 text-primary" : "text-muted-foreground hover:text-foreground",
          )}
        >
          {f.label}
        </button>
      ))}
    </div>
  );
}
