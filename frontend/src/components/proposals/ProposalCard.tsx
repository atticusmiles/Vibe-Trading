import { ConfidenceDot } from "@/components/fact-tables/ConfidenceDot";
import type { ProposalItem } from "@/lib/api";
import { cn } from "@/lib/utils";

const ACTION_LABELS: Record<string, string> = { create: "新增", update: "更新", delete: "删除" };
const ACTION_COLORS: Record<string, string> = {
  create: "bg-blue-500/15 text-blue-500",
  update: "bg-orange-500/15 text-orange-500",
  delete: "bg-red-500/15 text-red-500",
};

interface Props {
  proposal: ProposalItem;
  onAdopt: () => void;
  onReject: () => void;
  onViewDetail: () => void;
}

export function ProposalCard({ proposal, onAdopt, onReject, onViewDetail }: Props) {
  return (
    <div className="flex items-center gap-3 rounded-md border px-3 py-2">
      <span className={cn("shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium", ACTION_COLORS[proposal.action])}>
        {ACTION_LABELS[proposal.action]}
      </span>
      <span className="min-w-0 flex-1 truncate text-sm">{proposal.title}</span>
      <ConfidenceDot value={proposal.confidence} />
      {proposal.source_agent && <span className="shrink-0 text-[10px] text-muted-foreground">{proposal.source_agent}</span>}
      <div className="flex shrink-0 gap-1">
        <button onClick={onAdopt} className="rounded px-2 py-0.5 text-xs font-medium text-success hover:bg-success/10">采纳</button>
        <button onClick={onReject} className="rounded px-2 py-0.5 text-xs font-medium text-destructive hover:bg-destructive/10">拒绝</button>
        <button onClick={onViewDetail} className="rounded px-2 py-0.5 text-xs text-primary hover:underline">详情</button>
      </div>
    </div>
  );
}
