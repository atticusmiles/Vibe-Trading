import { ConfidenceDot } from "@/components/fact-tables/ConfidenceDot";
import { StatusDot } from "@/components/fact-tables/StatusDot";
import type { ProposalItem, ProposalListResponse } from "@/lib/api";
import { cn } from "@/lib/utils";
import { ChevronLeft, ChevronRight, FileCheck } from "lucide-react";
import { EmptyState } from "@/components/fact-tables/EmptyState";

const ACTION_LABELS: Record<string, string> = { create: "新增", update: "更新", delete: "删除" };
const ACTION_COLORS: Record<string, string> = {
  create: "bg-blue-500/15 text-blue-500",
  update: "bg-orange-500/15 text-orange-500",
  delete: "bg-red-500/15 text-red-500",
};
const TYPE_LABELS: Record<string, string> = { trend: "趋势", industry: "行业", stock: "自选股" };

interface Props {
  data: ProposalListResponse;
  onPageChange: (page: number) => void;
  onAdopt: (id: number) => void;
  onReject: (id: number) => void;
  onViewDetail: (proposal: ProposalItem) => void;
  loading?: boolean;
}

export function ProposalList({ data, onPageChange, onAdopt, onReject, onViewDetail, loading }: Props) {
  if (!loading && data.items.length === 0) {
    return <EmptyState icon={FileCheck} message="暂无提案" />;
  }

  const totalPages = Math.ceil(data.total / data.per_page);

  return (
    <div>
      <div className="space-y-1">
        {data.items.map((p) => (
          <div
            key={p.id}
            onClick={() => onViewDetail(p)}
            className="flex cursor-pointer items-center gap-3 rounded-md px-3 py-2 text-sm transition hover:bg-muted/50"
          >
            <span className={cn("shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium", ACTION_COLORS[p.action])}>
              {ACTION_LABELS[p.action]}
            </span>
            <span className="min-w-0 flex-1 truncate">{p.title}</span>
            <span className="shrink-0 text-[10px] text-muted-foreground">{TYPE_LABELS[p.target_type]}</span>
            <ConfidenceDot value={p.confidence} />
            <StatusDot status={p.status} />
            {p.status === "pending" && (
              <div className="flex shrink-0 gap-1">
                <button
                  onClick={(e) => { e.stopPropagation(); onAdopt(p.id); }}
                  className="rounded px-2 py-0.5 text-[10px] font-medium text-success hover:bg-success/10"
                >
                  采纳
                </button>
                <button
                  onClick={(e) => { e.stopPropagation(); onReject(p.id); }}
                  className="rounded px-2 py-0.5 text-[10px] font-medium text-destructive hover:bg-destructive/10"
                >
                  拒绝
                </button>
              </div>
            )}
          </div>
        ))}
      </div>
      {totalPages > 1 && (
        <div className="mt-3 flex items-center justify-between text-xs text-muted-foreground">
          <span>第 {data.page} 页，共 {data.total} 条</span>
          <div className="flex gap-1">
            <button
              onClick={() => onPageChange(data.page - 1)}
              disabled={data.page <= 1}
              className="rounded border p-1 hover:bg-muted disabled:opacity-30"
            >
              <ChevronLeft className="h-3.5 w-3.5" />
            </button>
            <button
              onClick={() => onPageChange(data.page + 1)}
              disabled={data.page >= totalPages}
              className="rounded border p-1 hover:bg-muted disabled:opacity-30"
            >
              <ChevronRight className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
