import { SearchInput } from "@/components/fact-tables/SearchInput";
import { StatusDot } from "@/components/fact-tables/StatusDot";
import { ConfidenceDot } from "@/components/fact-tables/ConfidenceDot";
import { CompactList } from "@/components/fact-tables/CompactList";
import { DetailPanel } from "@/components/fact-tables/DetailPanel";
import { EmptyState } from "@/components/fact-tables/EmptyState";
import { api, type CandidateResponse } from "@/lib/api";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { FlaskConical, Play, RefreshCw, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

const STATUS_OPTIONS: { label: string; value: string }[] = [
  { label: "待研究", value: "pending" },
  { label: "研究中", value: "researching" },
  { label: "已提案", value: "proposed" },
  { label: "已跳过", value: "passed" },
];

const STATUS_LABELS: Record<string, string> = {
  pending: "待研究",
  researching: "研究中",
  proposed: "已提案",
  passed: "已跳过",
};

const TYPE_LABELS: Record<string, string> = {
  trend: "趋势",
  industry: "行业",
  stock: "股票",
};

const MarkdownBlock = ({ content }: { content: string }) => (
  <div className="prose prose-sm dark:prose-invert max-w-none text-sm">
    <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
  </div>
);

export function CandidatesTab({ targetType }: { targetType: "trend" | "industry" | "stock" }) {
  const [candidates, setCandidates] = useState<CandidateResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [researching, setResearching] = useState(false);
  const [scanning, setScanning] = useState(false);

  // Scan log dialog
  const [logOpen, setLogOpen] = useState(false);
  const [logRunId, setLogRunId] = useState<string | null>(null);
  const [logs, setLogs] = useState<{ time: string; type: string; text: string }[]>([]);
  const logEndRef = useRef<HTMLDivElement>(null);
  const esRef = useRef<EventSource | null>(null);

  const SCAN_TYPE: Record<string, "trends" | "industries" | "stocks"> = {
    trend: "trends",
    industry: "industries",
    stock: "stocks",
  };

  const fetchCandidates = useCallback(async () => {
    setLoading(true);
    try {
      const result = await api.listCandidates({
        target_type: targetType,
        ...(statusFilter ? { candidate_status: statusFilter } : {}),
        per_page: 50,
      });
      setCandidates(result.items);
    } catch {
      toast.error("候选加载失败");
    } finally {
      setLoading(false);
    }
  }, [targetType, statusFilter]);

  useEffect(() => { fetchCandidates(); }, [fetchCandidates]);

  const closeLog = useCallback(() => {
    esRef.current?.close();
    esRef.current = null;
    setLogOpen(false);
    setLogRunId(null);
  }, []);

  const connectRunLog = useCallback((runId: string) => {
    esRef.current?.close();
    setLogs([]);
    setLogRunId(runId);
    setLogOpen(true);

    const token = localStorage.getItem("api_auth_key") || "";
    const url = `/swarm/runs/${runId}/events?token=${encodeURIComponent(token)}`;
    const source = new EventSource(url);
    esRef.current = source;

    const append = (type: string, data: string) => {
      const time = new Date().toLocaleTimeString();
      setLogs((prev) => [...prev, { time, type, text: data }]);
    };

    source.addEventListener("text_delta", (e) => {
      try { const d = JSON.parse(e.data); append("输出", d.text || d.delta || ""); } catch { append("输出", e.data); }
    });
    source.addEventListener("tool_call", (e) => {
      try { const d = JSON.parse(e.data); append("工具", `调用 ${d.name || d.tool || ""}(${(d.arguments || d.args || "").slice(0, 120)})`); } catch { append("工具", e.data); }
    });
    source.addEventListener("tool_result", (e) => {
      try { const d = JSON.parse(e.data); append("结果", (d.output || d.result || "").slice(0, 200)); } catch { append("结果", e.data); }
    });
    source.addEventListener("attempt.completed", (e) => {
      try { const d = JSON.parse(e.data); append("完成", d.agent_id ? `Agent ${d.agent_id} 完成` : "步骤完成"); } catch { append("完成", e.data); }
    });
    source.addEventListener("attempt.failed", (e) => {
      try { const d = JSON.parse(e.data); append("失败", d.error || "步骤失败"); } catch { append("失败", e.data); }
    });
    source.addEventListener("done", () => {
      append("结束", "运行完成");
      source.close();
      esRef.current = null;
      fetchCandidates();
    });
    source.onerror = () => {};
  }, [fetchCandidates]);

  useEffect(() => { logEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [logs]);
  useEffect(() => () => { esRef.current?.close(); }, []);

  const handleScan = async () => {
    setScanning(true);
    try {
      const result = await api.triggerScan(SCAN_TYPE[targetType]);
      if (result.run_id) connectRunLog(result.run_id);
      setTimeout(fetchCandidates, 8000);
    } catch {
      toast.error("触发扫描失败");
    } finally {
      setScanning(false);
    }
  };

  const filtered = useMemo(() => {
    if (!search) return candidates;
    const q = search.toLowerCase();
    return candidates.filter(
      (c) => c.name.toLowerCase().includes(q) || (c.code || "").toLowerCase().includes(q),
    );
  }, [candidates, search]);

  const selected = useMemo(() => candidates.find((c) => c.id === selectedId) ?? null, [candidates, selectedId]);

  const toggleSelect = (id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const handleBatchResearch = async () => {
    const ids = Array.from(selectedIds);
    if (ids.length === 0) return;
    setResearching(true);
    try {
      const result = await api.batchResearch(ids);
      toast.success(`已触发 ${result.triggered} 个研究任务`);
      setSelectedIds(new Set());
      fetchCandidates();
    } catch {
      toast.error("触发研究失败");
    } finally {
      setResearching(false);
    }
  };

  const handleResearchOne = async (id: number) => {
    setResearching(true);
    try {
      await api.batchResearch([id]);
      toast.success("研究任务已触发");
      fetchCandidates();
    } catch {
      toast.error("触发研究失败");
    } finally {
      setResearching(false);
    }
  };

  const parseExtraReports = (raw: string): string[] => {
    try { return JSON.parse(raw); } catch { return []; }
  };

  const LOG_COLORS: Record<string, string> = {
    "输出": "text-foreground",
    "工具": "text-blue-500",
    "结果": "text-green-600",
    "完成": "text-purple-500",
    "失败": "text-destructive",
    "结束": "text-yellow-600",
  };

  return (
    <div className="flex h-full flex-col gap-3">
      {/* Toolbar */}
      <div className="flex items-center gap-2">
        <div className="flex-1">
          <SearchInput value={search} onChange={setSearch} />
        </div>
        <button
          onClick={handleScan}
          disabled={scanning}
          className="inline-flex items-center gap-1 rounded-md border px-2 py-1.5 text-xs text-muted-foreground hover:bg-muted disabled:opacity-50"
        >
          <RefreshCw className={`h-3 w-3 ${scanning ? "animate-spin" : ""}`} /> {scanning ? "扫描中..." : "扫描"}
        </button>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="rounded-md border bg-background px-2 py-1.5 text-xs text-muted-foreground outline-none"
        >
          <option value="">全部状态</option>
          {STATUS_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
        {selectedIds.size > 0 && (
          <button
            onClick={handleBatchResearch}
            disabled={researching}
            className="inline-flex items-center gap-1 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
          >
            <Play className="h-3 w-3" /> {researching ? "启动中..." : `研究 (${selectedIds.size})`}
          </button>
        )}
      </div>

      {/* Master-Detail */}
      <div className="flex min-h-0 flex-1 gap-px rounded-lg border bg-border">
        {/* List */}
        <div className="flex w-[40%] min-w-0 flex-col bg-card">
          {filtered.length === 0 ? (
            <EmptyState icon={FlaskConical} message="暂无候选" />
          ) : (
            <CompactList
              items={filtered}
              selectedId={selectedId}
              onSelect={setSelectedId}
              getId={(c) => c.id}
              renderRow={(c) => (
                <div className="flex flex-col gap-0.5">
                  <div className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={selectedIds.has(c.id)}
                      onChange={(e) => { e.stopPropagation(); toggleSelect(c.id); }}
                      className="h-3 w-3 shrink-0 accent-primary"
                      onClick={(e) => e.stopPropagation()}
                    />
                    <StatusDot status={c.status} />
                    <span className="min-w-0 flex-1 truncate text-sm">{c.name}</span>
                    <ConfidenceDot value={c.initial_score} />
                  </div>
                  <span className="pl-7 text-[10px] text-muted-foreground">
                    {c.code ? `${c.code} · ` : ""}{c.created_at?.slice(0, 10) || ""}
                  </span>
                </div>
              )}
              actions={() => null}
            />
          )}
        </div>

        {/* Detail */}
        <div className="flex flex-1 flex-col bg-card">
          <DetailPanel isEmpty={!selected}>
            {selected ? (
              <div className="space-y-5 overflow-y-auto p-5">
                {/* Header */}
                <div className="space-y-3">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <h2 className="text-lg font-semibold leading-tight">{selected.name}</h2>
                      {selected.code && (
                        <span className="mt-0.5 inline-block rounded bg-muted px-2 py-0.5 text-xs text-muted-foreground">{selected.code}</span>
                      )}
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      <StatusDot status={selected.status} />
                      <span className="text-xs text-muted-foreground">{STATUS_LABELS[selected.status] || selected.status}</span>
                      {selected.status === "pending" && (
                        <button
                          onClick={() => handleResearchOne(selected.id)}
                          disabled={researching}
                          className="ml-1 inline-flex items-center gap-1 rounded-md bg-primary px-2.5 py-1 text-xs font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
                        >
                          <Play className="h-3 w-3" /> {researching ? "启动中..." : "开始研究"}
                        </button>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-1 text-xs">
                    <span className="text-muted-foreground">置信度</span>
                    <ConfidenceDot value={selected.initial_score} />
                    <span className="text-muted-foreground">{selected.initial_score}/10</span>
                  </div>
                </div>

                {/* Source Context */}
                {selected.source_context && (
                  <div className="rounded-lg border p-3">
                    <p className="mb-1.5 text-xs font-semibold text-muted-foreground">来源上下文</p>
                    <pre className="max-h-28 overflow-auto whitespace-pre-wrap rounded bg-muted/50 p-2.5 text-xs leading-relaxed">{selected.source_context}</pre>
                  </div>
                )}

                {/* Conclusion */}
                {selected.conclusion && (
                  <div className="rounded-lg border p-3">
                    <p className="mb-1.5 text-xs font-semibold text-muted-foreground">结论</p>
                    <MarkdownBlock content={selected.conclusion} />
                  </div>
                )}

                {/* Main Report */}
                {selected.report && (
                  <div className="rounded-lg border p-3">
                    <p className="mb-1.5 text-xs font-semibold text-muted-foreground">
                      研究报告{selected.report_type ? ` · ${selected.report_type}` : ""}
                    </p>
                    <MarkdownBlock content={selected.report} />
                  </div>
                )}

                {/* Extra Reports */}
                {(() => {
                  const extras = parseExtraReports(selected.extra_reports);
                  if (extras.length === 0) return null;
                  return (
                    <div className="rounded-lg border p-3">
                      <p className="mb-2 text-xs font-semibold text-muted-foreground">补充报告 ({extras.length})</p>
                      <div className="space-y-3">
                        {extras.map((r, i) => (
                          <div key={i} className="rounded-md bg-muted/30 p-3">
                            <MarkdownBlock content={typeof r === "string" ? r : JSON.stringify(r, null, 2)} />
                          </div>
                        ))}
                      </div>
                    </div>
                  );
                })()}

                {/* Metadata */}
                <div className="border-t pt-3 text-xs text-muted-foreground">
                  <div className="grid grid-cols-2 gap-x-4 gap-y-1">
                    <span>创建：{selected.created_at?.slice(0, 19).replace("T", " ") || "—"}</span>
                    {selected.updated_at && <span>更新：{selected.updated_at?.slice(0, 19).replace("T", " ")}</span>}
                    {selected.source_run_id && <span>来源 Run：<code className="text-[10px]">{selected.source_run_id.slice(0, 20)}...</code></span>}
                    {selected.research_run_id && <span>研究 Run：<code className="text-[10px]">{selected.research_run_id.slice(0, 20)}...</code></span>}
                    {selected.proposal_id && <span>关联提案：#{selected.proposal_id}</span>}
                  </div>
                </div>
              </div>
            ) : null}
          </DetailPanel>
        </div>
      </div>

      {/* Scan Log Dialog */}
      {logOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="flex max-h-[80vh] w-[700px] flex-col rounded-lg border bg-card shadow-xl">
            <div className="flex items-center justify-between border-b px-4 py-3">
              <h3 className="text-sm font-semibold">扫描运行日志 {logRunId ? `(${logRunId.slice(0, 16)}...)` : ""}</h3>
              <button onClick={closeLog} className="rounded p-1 text-muted-foreground hover:bg-muted">
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="flex-1 overflow-auto bg-zinc-950 p-4 font-mono text-xs leading-relaxed">
              {logs.length === 0 ? (
                <span className="text-zinc-500">等待事件...</span>
              ) : (
                logs.map((l, i) => (
                  <div key={i} className="flex gap-2 py-0.5">
                    <span className="shrink-0 text-zinc-500">{l.time}</span>
                    <span className={`shrink-0 w-10 ${LOG_COLORS[l.type] || "text-zinc-400"}`}>[{l.type}]</span>
                    <span className="whitespace-pre-wrap text-zinc-300">{l.text}</span>
                  </div>
                ))
              )}
              <div ref={logEndRef} />
            </div>
            <div className="border-t px-4 py-2 text-[10px] text-muted-foreground">
              {logs.length} 条日志 · SSE 实时流
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
