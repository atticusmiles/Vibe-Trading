import type { LucideIcon } from "lucide-react";
import { PlusCircle } from "lucide-react";

export function EmptyState({ icon: Icon, message, action }: { icon?: LucideIcon; message: string; action?: { label: string; onClick: () => void } }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-3 p-8 text-muted-foreground">
      {Icon && <Icon className="h-10 w-10" />}
      <p className="text-sm">{message}</p>
      {action && (
        <button onClick={action.onClick} className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90">
          <PlusCircle className="h-3.5 w-3.5" /> {action.label}
        </button>
      )}
    </div>
  );
}
