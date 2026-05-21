import { ConfidenceDot } from "@/components/fact-tables/ConfidenceDot";
import type { ProposalItem } from "@/lib/api";
import { X } from "lucide-react";

const ACTION_LABELS: Record<string, string> = { create: "新增", update: "更新", delete: "删除" };
const TYPE_LABELS: Record<string, string> = { trend: "趋势", industry: "行业", stock: "自选股" };

interface Props {
  open: boolean;
  onClose: () => void;
  proposal: ProposalItem | null;
  factItem: Record<string, unknown> | null;
  onAdopt: (id: number) => void;
  onReject: (id: number) => void;
}

function parseJsonSafe(s: string | null): Record<string, unknown> {
  if (!s) return {};
  try { return JSON.parse(s); } catch { return {}; }
}

export function ProposalDetailModal({ open, onClose, proposal, factItem, onAdopt, onReject }: Props) {
  if (!open || !proposal) return null;

  const payload = parseJsonSafe(proposal.payload);
  const original = parseJsonSafe(proposal.original_payload);
  const isUpdate = proposal.action === "update";
  const isCreate = proposal.action === "create";
  const isDelete = proposal.action === "delete";

  const allKeys = isUpdate
    ? [...new Set([...Object.keys(original), ...Object.keys(payload)])]
    : Object.keys(payload);

  const FIELD_LABELS: Record<string, string> = {
    title: "标题", name: "名称", level: "级别", evidence: "证据",
    confidence: "置信度", reason: "原因", code: "代码",
    industry_name: "行业", position: "仓位", advice: "建议",
    target_price: "目标价", stop_loss: "止损价",
    research_report: "研究报告", recommended_stocks: "推荐股票",
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div
        className="max-h-[80vh] w-full max-w-lg overflow-y-auto overflow-x-hidden rounded-lg border bg-card p-5 shadow-lg break-words"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between">
          <h2 className="text-base font-semibold">提案详情</h2>
          <button onClick={onClose} className="rounded p-1 hover:bg-muted"><X className="h-4 w-4" /></button>
        </div>

        <div className="mt-3 space-y-2 text-sm">
          <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
            <span>类型：{TYPE_LABELS[proposal.target_type]}</span>
            <span>·</span>
            <span>操作：{ACTION_LABELS[proposal.action]}</span>
          </div>
          <p className="font-medium">{proposal.title}</p>
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground">置信度：</span>
            <ConfidenceDot value={proposal.confidence} />
          </div>
          {proposal.source_agent && <p className="text-xs text-muted-foreground">来源：{proposal.source_agent}</p>}
          {proposal.run_id && <p className="text-xs text-muted-foreground">运行：{proposal.run_id}</p>}
          {proposal.summary && (
            <div className="mt-2 min-w-0">
              <p className="text-xs font-medium text-muted-foreground">变更摘要：</p>
              <p className="mt-1 whitespace-pre-wrap break-words text-muted-foreground">{proposal.summary}</p>
            </div>
          )}
        </div>

        {/* Field comparison */}
        {!isDelete && allKeys.length > 0 && (
          <div className="mt-4 border-t pt-3">
            {isUpdate ? (
              <div className="grid grid-cols-2 gap-3 min-w-0">
                <div className="min-w-0">
                  <p className="mb-1 text-xs font-medium text-muted-foreground">当前值</p>
                  {allKeys.map((k) => (
                    <div key={k} className="flex justify-between gap-2 border-b py-1 text-xs">
                      <span className="text-muted-foreground shrink-0">{FIELD_LABELS[k] || k}</span>
                      <span className="break-all text-right min-w-0">{String(original[k] ?? "—")}</span>
                    </div>
                  ))}
                </div>
                <div>
                  <p className="mb-1 text-xs font-medium text-muted-foreground">提议值</p>
                  {allKeys.map((k) => (
                    <div key={k} className="flex justify-between gap-2 border-b py-1 text-xs">
                      <span className="text-muted-foreground shrink-0">{FIELD_LABELS[k] || k}</span>
                      <span className="font-medium break-all text-right min-w-0">{String(payload[k] ?? "—")}</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : isCreate ? (
              <div>
                <p className="mb-1 text-xs font-medium text-muted-foreground">新增内容</p>
                {allKeys.map((k) => (
                  <div key={k} className="flex justify-between border-b py-1 text-xs">
                    <span className="text-muted-foreground">{FIELD_LABELS[k] || k}</span>
                    <span className="font-medium">{String(payload[k] ?? "—")}</span>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        )}

        {isDelete && (
          <p className="mt-3 text-sm text-destructive">此操作将删除该条目。</p>
        )}

        <div className="mt-4 flex gap-2 border-t pt-3">
          <button
            onClick={() => { onAdopt(proposal.id); onClose(); }}
            className="rounded-md bg-success px-4 py-1.5 text-sm font-medium text-white hover:opacity-90"
          >
            采纳
          </button>
          <button
            onClick={() => { onReject(proposal.id); onClose(); }}
            className="rounded-md bg-destructive px-4 py-1.5 text-sm font-medium text-white hover:opacity-90"
          >
            拒绝
          </button>
          <button onClick={onClose} className="rounded-md border px-4 py-1.5 text-sm hover:bg-muted">关闭</button>
        </div>
      </div>
    </div>
  );
}
