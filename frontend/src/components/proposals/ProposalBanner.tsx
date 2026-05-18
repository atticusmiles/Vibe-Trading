import { ProposalCard } from "./ProposalCard";
import type { ProposalItem } from "@/lib/api";
import { ChevronDown, ChevronUp, AlertTriangle } from "lucide-react";
import { useState } from "react";

interface Props {
  target_type: "trend" | "industry" | "stock";
  proposals: ProposalItem[];
  onAdopt: (id: number) => void;
  onReject: (id: number) => void;
  onViewDetail: (proposal: ProposalItem) => void;
}

export function ProposalBanner({ proposals, onAdopt, onReject, onViewDetail }: Props) {
  const [open, setOpen] = useState(false);

  if (proposals.length === 0) return null;

  return (
    <div className="rounded-lg border border-warning/30 bg-warning/5">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm"
      >
        <AlertTriangle className="h-4 w-4 text-warning" />
        <span className="flex-1 font-medium">{proposals.length} 条待审批提案</span>
        {open ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
      </button>
      {open && (
        <div className="space-y-1 border-t px-3 py-2">
          {proposals.map((p) => (
            <ProposalCard
              key={p.id}
              proposal={p}
              onAdopt={() => onAdopt(p.id)}
              onReject={() => onReject(p.id)}
              onViewDetail={() => onViewDetail(p)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
