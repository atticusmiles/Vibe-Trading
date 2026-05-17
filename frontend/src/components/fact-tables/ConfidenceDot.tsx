import { cn } from "@/lib/utils";

function confColor(v: number): string {
  if (v <= 3) return "bg-danger";
  if (v <= 6) return "bg-warning";
  return "bg-success";
}

export function ConfidenceDot({ value }: { value: number }) {
  return (
    <span className="inline-flex items-center gap-1">
      <span className={cn("inline-block h-2 w-2 rounded-full", confColor(value))} />
      <span className="text-xs text-muted-foreground">{value}</span>
    </span>
  );
}
