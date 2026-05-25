import { SearchInput } from "@/components/fact-tables/SearchInput";
import { StatusDot } from "@/components/fact-tables/StatusDot";
import { ConfidenceDot } from "@/components/fact-tables/ConfidenceDot";
import { CompactList } from "@/components/fact-tables/CompactList";
import { DetailPanel } from "@/components/fact-tables/DetailPanel";
import { EmptyState } from "@/components/fact-tables/EmptyState";
import { api, type CandidateResponse, type SwarmRunSummary } from "@/lib/api";
import { getApiAuthKey } from "@/lib/apiAuth";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Clock, FlaskConical, Play, RefreshCw, RotateCw, X } from "lucide-react";
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
  const [logTitle, setLogTitle] = useState("");
  const [logs, setLogs] = useState<{ time: string; type: string; text: string; iter?: number }[]>([]);
  const logEndRef = useRef<HTMLDivElement>(null);
  const esRef = useRef<EventSource | null>(null);

  // History dialog
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyRuns, setHistoryRuns] = useState<SwarmRunSummary[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);

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
    setLogTitle("");
  }, []);

  const toBeijingTime = (ts?: string) => {
    if (!ts) return new Date().toLocaleTimeString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false });
    return new Date(ts).toLocaleTimeString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false });
  };

  const connectRunLog = useCallback((runId: string, title?: string) => {
    esRef.current?.close();
    setLogs([]);
    setLogRunId(runId);
    setLogTitle(title || "");
    setLogOpen(true);

    const token = getApiAuthKey();
    const url = `/swarm/runs/${runId}/events?token=${encodeURIComponent(token)}`;
    const source = new EventSource(url);
    esRef.current = source;

    const append = (type: string, data: string, iter?: number) => {
      const time = toBeijingTime();
      setLogs((prev) => {
        // Merge consecutive worker_text chunks with the same iteration
        if (type === "输出") {
          const last = prev[prev.length - 1];
          if (last && last.type === "输出" && last.iter === iter) {
            return prev.map((e, i) =>
              i === prev.length - 1 ? { ...e, text: e.text + data } : e
            );
          }
        }
        return [...prev, { time, type, text: data, iter }];
      });
    };

    // Parse SwarmEvent JSON payload → { type, agent_id, task_id, data, timestamp }
    const parseSwarmEvent = (raw: string): Record<string, unknown> => {
      try { return JSON.parse(raw); } catch { return { type: "unknown", data: { raw } }; }
    };

    const handleEvent = (evt: Record<string, unknown>) => {
      const etype = (evt.type as string) || "unknown";
      const agent = (evt.agent_id as string) || "";
      const data = (evt.data || {}) as Record<string, unknown>;

      switch (etype) {
        case "run_started":
          append("启动", "扫描运行已开始");
          break;
        case "layer_started": {
          const layer = data.layer as number;
          const tasks = (data.tasks as string[])?.join(", ") || "";
          append("层级", `第 ${layer} 层开始 (${tasks})`);
          break;
        }
        case "task_started":
          append("任务", `开始执行 (Agent: ${agent})`);
          break;
        case "task_retry": {
          const attempt = data.attempt as number;
          const maxRetries = data.max_retries as number;
          const prevErr = (data.previous_error as string)?.slice(0, 100) || "";
          append("重试", `第 ${attempt}/${maxRetries + 1} 次${prevErr ? ` (原因: ${prevErr})` : ""}`);
          break;
        }
        case "worker_started":
          append("Agent", `${agent} 开始工作`);
          break;
        case "worker_text": {
          const content = (data.content as string) || "";
          const iter = data.iteration as number;
          append("输出", content, iter);
          break;
        }
        case "tool_call": {
          const tool = (data.tool as string) || "unknown";
          const iter = data.iteration as number;
          append("工具", `调用 ${tool}`, iter);
          break;
        }
        case "tool_result": {
          const tool = (data.tool as string) || "unknown";
          const elapsed = data.elapsed_ms as number;
          append("结果", `${tool} 完成 (${elapsed}ms)`);
          break;
        }
        case "worker_completed": {
          const iterations = data.iterations as number;
          append("Agent", `${agent} 完成 (${iterations} 轮)`);
          break;
        }
        case "task_completed": {
          const summary = (data.summary as string)?.slice(0, 200) || "";
          append("完成", `任务完成${summary ? ` — ${summary}` : ""}`);
          break;
        }
        case "worker_failed":
        case "task_failed": {
          const err = (data.error as string)?.slice(0, 200) || "未知错误";
          append("失败", `${agent || "任务"} 失败: ${err}`);
          break;
        }
        case "worker_timeout": {
          const elapsed = data.elapsed as number;
          append("超时", `${agent} 超时 (${elapsed}s)`);
          break;
        }
        case "worker_iteration_limit":
          append("限制", `${agent} 达到迭代上限`);
          break;
        case "run_completed": {
          const status = (data.status as string) || "completed";
          append("完成", `扫描完成 (${status})`);
          break;
        }
        case "run_error": {
          const err = (data.error as string)?.slice(0, 200) || "未知错误";
          append("错误", `运行异常: ${err}`);
          break;
        }
        default:
          append("事件", `${etype}${agent ? ` (${agent})` : ""}`);
      }
    };

    // Register listeners for all known swarm event types
    const knownTypes = [
      "run_started", "layer_started",
      "task_started", "task_retry", "task_completed", "task_failed",
      "worker_started", "worker_text", "worker_completed",
      "worker_failed", "worker_timeout", "worker_iteration_limit",
      "tool_call", "tool_result",
      "run_completed", "run_error",
    ];

    for (const etype of knownTypes) {
      source.addEventListener(etype, (e) => {
        handleEvent(parseSwarmEvent(e.data));
      });
    }

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
      if (result.run_id) connectRunLog(result.run_id, `${TYPE_LABELS[targetType]}扫描`);
      setTimeout(fetchCandidates, 8000);
    } catch {
      toast.error("触发扫描失败");
    } finally {
      setScanning(false);
    }
  };

  const SCAN_PRESET_MAP: Record<string, string> = {
    trend: "scan_trends",
    industry: "scan_industries",
    stock: "scan_stocks",
  };

  const fetchHistory = async () => {
    setHistoryLoading(true);
    setHistoryOpen(true);
    try {
      const runs = await api.listSwarmRuns();
      const targetPreset = SCAN_PRESET_MAP[targetType];
      setHistoryRuns(runs.filter((r) => r.preset_name === targetPreset));
    } catch {
      toast.error("加载历史失败");
    } finally {
      setHistoryLoading(false);
    }
  };

  const SCAN_PRESET_LABELS: Record<string, string> = {
    scan_trends: "趋势扫描",
    scan_industries: "行业扫描",
    scan_stocks: "股票扫描",
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
      toast.success(`已触发 ${result.total} 个研究任务${result.skipped > 0 ? `，${result.skipped} 个跳过` : ""}`);
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
        <button
          onClick={fetchHistory}
          className="inline-flex items-center gap-1 rounded-md border px-2 py-1.5 text-xs text-muted-foreground hover:bg-muted"
        >
          <Clock className="h-3 w-3" /> 历史
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
              renderRow={(c) => {
                const resultText = c.conclusion || c.report || "";
                return (
                  <div className="flex flex-col gap-0.5 py-0.5">
                    <div className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={selectedIds.has(c.id)}
                        onChange={(e) => { e.stopPropagation(); toggleSelect(c.id); }}
                        className="h-3 w-3 shrink-0 accent-primary"
                        onClick={(e) => e.stopPropagation()}
                      />
                      <StatusDot status={c.status} />
                      <span className={`inline-flex items-center rounded px-1 py-0.5 text-[10px] font-medium leading-tight ${
                        c.status === "pending" ? "bg-muted text-muted-foreground" :
                        c.status === "researching" ? "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300" :
                        c.status === "proposed" ? "bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300" :
                        c.status === "passed" ? "bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300" :
                        "bg-muted text-muted-foreground"
                      }`}>
                        {STATUS_LABELS[c.status] || c.status}
                      </span>
                      <span className="min-w-0 flex-1 truncate text-sm font-medium">{c.name}</span>
                      <span className="inline-flex items-center gap-1 shrink-0">
                        <span className={`inline-block h-2 w-2 rounded-full ${
                          c.initial_score <= 3 ? "bg-red-500" :
                          c.initial_score <= 6 ? "bg-yellow-500" :
                          "bg-green-500"
                        }`} />
                        <span className="text-xs tabular-nums text-muted-foreground">{c.initial_score}/10</span>
                      </span>
                    </div>
                    <div className="flex items-center gap-1 pl-[52px] text-[10px] text-muted-foreground">
                      {c.code && <span className="font-mono">{c.code}</span>}
                      {c.code && <span>·</span>}
                      <span>{c.created_at?.slice(0, 10) || ""}</span>
                    </div>
                    {c.status === "researching" ? (
                      <div className="pl-[52px] flex items-center gap-1.5 text-[10px] leading-tight text-blue-500">
                        <span className="inline-block h-1.5 w-1.5 rounded-full bg-blue-500 animate-pulse" />
                        <span>研究进行中...</span>
                        {c.research_run_id && (
                          <span className="text-muted-foreground/50 font-mono">({c.research_run_id.slice(0, 12)}...)</span>
                        )}
                      </div>
                    ) : resultText && c.status !== "pending" ? (
                      <div className="pl-[52px] text-[10px] leading-tight text-muted-foreground/70 line-clamp-1">
                        {resultText.slice(0, 90).replace(/\n/g, " ").trim()}
                        {resultText.length > 90 ? "..." : ""}
                      </div>
                    ) : null}
                  </div>
                );
              }}
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
                      {selected.research_run_id && (
                        <button
                          onClick={() => connectRunLog(selected.research_run_id!, `${selected.name} 研究日志`)}
                          className="inline-flex items-center gap-1 rounded-md border px-2 py-1 text-[10px] text-muted-foreground hover:bg-muted"
                        >
                          <Clock className="h-3 w-3" /> 研究日志
                        </button>
                      )}
                      {selected.status === "pending" ? (
                        <button
                          onClick={() => handleResearchOne(selected.id)}
                          disabled={researching}
                          className="ml-1 inline-flex items-center gap-1 rounded-md bg-primary px-2.5 py-1 text-xs font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
                        >
                          <Play className="h-3 w-3" /> {researching ? "启动中..." : "开始研究"}
                        </button>
                      ) : selected.status !== "researching" && (
                        <button
                          onClick={() => handleResearchOne(selected.id)}
                          disabled={researching}
                          className="ml-1 inline-flex items-center gap-1 rounded-md border border-primary/50 px-2.5 py-1 text-xs font-medium text-primary hover:bg-primary/10 disabled:opacity-50"
                        >
                          <RotateCw className={`h-3 w-3 ${researching ? "animate-spin" : ""}`} /> {researching ? "启动中..." : "重新研究"}
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
                        {extras.map((r, i) => {
                          if (typeof r === "string") {
                            return <div key={i} className="rounded-md bg-muted/30 p-3"><MarkdownBlock content={r} /></div>;
                          }
                          const agentId = (r as Record<string, unknown>).agent_id as string | undefined;
                          const title = (r as Record<string, unknown>).title as string | undefined;
                          const content = (r as Record<string, unknown>).content as string | undefined;
                          if (!content) {
                            return <div key={i} className="rounded-md bg-muted/30 p-3"><MarkdownBlock content={JSON.stringify(r, null, 2)} /></div>;
                          }
                          return (
                            <div key={i} className="rounded-md bg-muted/30 p-3">
                              {title && <p className="mb-1 text-sm font-semibold">{title}</p>}
                              {agentId && <p className="mb-2 text-[10px] text-muted-foreground/60">{agentId}</p>}
                              <MarkdownBlock content={content} />
                            </div>
                          );
                        })}
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

      {/* History Dialog */}
      {historyOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="flex max-h-[80vh] w-[600px] flex-col rounded-lg border bg-card shadow-xl">
            <div className="flex items-center justify-between border-b px-4 py-3">
              <h3 className="text-sm font-semibold">扫描历史记录</h3>
              <button onClick={() => setHistoryOpen(false)} className="rounded p-1 text-muted-foreground hover:bg-muted">
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="flex-1 overflow-auto">
              {historyLoading ? (
                <div className="flex items-center justify-center py-12 text-sm text-muted-foreground">加载中...</div>
              ) : historyRuns.length === 0 ? (
                <div className="flex items-center justify-center py-12 text-sm text-muted-foreground">暂无扫描记录</div>
              ) : (
                <div className="divide-y">
                  {historyRuns.map((run) => (
                    <button
                      key={run.id}
                      onClick={() => {
                        setHistoryOpen(false);
                        connectRunLog(run.id, SCAN_PRESET_LABELS[run.preset_name] || run.preset_name);
                      }}
                      className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-muted/50 transition-colors"
                    >
                      <span className={`h-2 w-2 shrink-0 rounded-full ${
                        run.status === "completed" ? "bg-green-500" :
                        run.status === "failed" ? "bg-destructive" :
                        run.status === "running" ? "bg-blue-500 animate-pulse" :
                        "bg-zinc-400"
                      }`} />
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm">{SCAN_PRESET_LABELS[run.preset_name] || run.preset_name}</p>
                        <p className="text-[10px] text-muted-foreground">
                          {run.created_at?.slice(0, 19).replace("T", " ") || ""} · {run.completed_count}/{run.task_count} 任务
                        </p>
                      </div>
                      <span className="shrink-0 text-[10px] text-muted-foreground">{run.status}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
            <div className="border-t px-4 py-2 text-[10px] text-muted-foreground">
              {historyRuns.length} 条记录 · 点击查看事件流
            </div>
          </div>
        </div>
      )}

      {/* Scan Log Dialog */}
      {logOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="flex max-h-[80vh] w-[700px] flex-col rounded-lg border bg-card shadow-xl">
            <div className="flex items-center justify-between border-b px-4 py-3">
              <h3 className="text-sm font-semibold">{logTitle || "运行日志"} {logRunId ? `(${logRunId.slice(0, 16)}...)` : ""}</h3>
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
                    <span className={`shrink-0 ${LOG_COLORS[l.type] || "text-zinc-400"}`}>[{l.type}]<span className="ml-1 text-zinc-500">{l.iter !== undefined && (i === 0 || logs[i-1].iter !== l.iter) ? "#" + l.iter : ""}</span></span>
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
