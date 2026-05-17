import { cn } from "@/lib/utils";

const STATUS_COLORS: Record<string, string> = {
  adopted: "bg-success",
  proposed: "bg-info",
  rejected: "bg-muted-foreground",
  removed: "border border-muted-foreground/40 bg-transparent",
};

export function StatusDot({ status, size = "sm" }: { status: string; size?: "sm" | "md" }) {
  const cls = size === "sm" ? "h-2 w-2" : "h-2.5 w-2.5";
  return <span className={cn("inline-block shrink-0 rounded-full", cls, STATUS_COLORS[status] || "bg-muted")} />;
}
