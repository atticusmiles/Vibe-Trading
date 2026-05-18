import { MasterDetailLayout } from "@/components/fact-tables/MasterDetailLayout";
import { SearchInput } from "@/components/fact-tables/SearchInput";
import { StatusDot } from "@/components/fact-tables/StatusDot";
import { ConfidenceDot } from "@/components/fact-tables/ConfidenceDot";
import { CompactList } from "@/components/fact-tables/CompactList";
import { DetailPanel } from "@/components/fact-tables/DetailPanel";
import { EmptyState } from "@/components/fact-tables/EmptyState";
import { ProposalDetailModal } from "@/components/proposals/ProposalDetailModal";
import { api, type ProposalItem, type ProposalListResponse } from "@/lib/api";
import { cn } from "@/lib/utils";
import { FileCheck, PlusCircle, Pencil, ChevronDown, Calendar } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

const ACTION_LABELS: Record<string, string> = { create: "新增", update: "更新", delete: "删除" };
const ACTION_COLORS: Record<string, string> = {
  create: "bg-blue-500/15 text-blue-500",
  update: "bg-orange-500/15 text-orange-500",
  delete: "bg-red-500/15 text-red-500",
};
const TYPE_LABELS: Record<string, string> = { trend: "趋势", industry: "行业", stock: "自选股" };
const STATUS_OPTIONS: { label: string; value: string }[] = [
  { label: "待审批", value: "pending" },
  { label: "已采纳", value: "adopted" },
  { label: "已拒绝", value: "rejected" },
  { label: "已取消", value: "cancelled" },
];
const LEVELS = ["long-term", "mid-term", "short-term"];
const LEVEL_LABELS: Record<string, string> = { "long-term": "长期", "mid-term": "中期", "short-term": "短期" };
const inputCls = "w-full rounded-md border bg-background px-3 py-1.5 text-sm outline-none focus:border-primary";

type Mode = "view" | "add";

const EMPTY_DATA: ProposalListResponse = { items: [], total: 0, page: 1, per_page: 50 };

/** Return ISO date string for N days ago. */
function daysAgo(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
}

export function Proposals() {
  const [data, setData] = useState<ProposalListResponse>(EMPTY_DATA);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [mode, setMode] = useState<Mode>("view");

  // Filters
  const [typeFilter, setTypeFilter] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [sinceDays, setSinceDays] = useState(30);
  const [statusOpen, setStatusOpen] = useState(false);
  const [dateOpen, setDateOpen] = useState(false);

  // Detail modal
  const [detailProposal, setDetailProposal] = useState<ProposalItem | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);

  // Common form state
  const [formType, setFormType] = useState<"trend" | "industry" | "stock">("trend");
  const [formAction, setFormAction] = useState<"create" | "update" | "delete">("create");
  const [formConfidence, setFormConfidence] = useState(5);
  const [formTargetId, setFormTargetId] = useState("");
  const [saving, setSaving] = useState(false);

  // Trend fields
  const [fTitle, setFTitle] = useState("");
  const [fLevel, setFLevel] = useState("mid-term");
  const [fEvidence, setFEvidence] = useState("");
  // Industry fields
  const [fName, setFName] = useState("");
  const [fReason, setFReason] = useState("");
  // Stock fields
  const [fCode, setFCode] = useState("");
  const [fIndustryName, setFIndustryName] = useState("");
  const [fAdvice, setFAdvice] = useState("");

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const result = await api.listProposals({
        ...(typeFilter ? { type: typeFilter } : {}),
        ...(statusFilter ? { status: statusFilter } : {}),
        since: daysAgo(sinceDays),
        per_page: 50,
      });
      setData(result);
    } catch {
      toast.error("提案列表加载失败");
    } finally {
      setLoading(false);
    }
  }, [typeFilter, statusFilter, sinceDays]);

  useEffect(() => { fetchData(); }, [fetchData]);

  // Close dropdowns on outside click
  useEffect(() => {
    if (!statusOpen && !dateOpen) return;
    const close = () => { setStatusOpen(false); setDateOpen(false); };
    document.addEventListener("click", close);
    return () => document.removeEventListener("click", close);
  }, [statusOpen, dateOpen]);

  const filtered = useMemo(() => {
    if (!search) return data.items;
    return data.items.filter(
      (p) => p.title.toLowerCase().includes(search.toLowerCase()) || (p.summary || "").toLowerCase().includes(search.toLowerCase()),
    );
  }, [data.items, search]);

  const selected = useMemo(() => data.items.find((p) => p.id === selectedId) ?? null, [data.items, selectedId]);

  const handleAdopt = async (id: number) => {
    try { await api.adoptProposal(id); toast.success("提案已采纳"); } catch { toast.error("采纳失败"); }
    fetchData();
  };
  const handleReject = async (id: number) => {
    try { await api.rejectProposal(id); toast.success("提案已拒绝"); } catch { toast.error("拒绝失败"); }
    fetchData();
  };

  const resetForm = () => {
    setFTitle(""); setFLevel("mid-term"); setFEvidence("");
    setFName(""); setFReason("");
    setFCode(""); setFIndustryName(""); setFAdvice("");
    setFormConfidence(5); setFormTargetId("");
  };

  const startAdd = () => {
    setSelectedId(null);
    resetForm();
    setFormType("trend"); setFormAction("create");
    setMode("add");
  };

  const buildPayload = (): string => {
    if (formAction === "delete") return "{}";
    switch (formType) {
      case "trend":
        return JSON.stringify({ title: fTitle.trim(), level: fLevel, evidence: fEvidence.trim() });
      case "industry":
        return JSON.stringify({ name: fName.trim(), reason: fReason.trim() });
      case "stock":
        return JSON.stringify({ code: fCode.trim(), name: fCode.trim(), industry_name: fIndustryName.trim(), advice: fAdvice.trim() });
    }
  };

  const getDisplayTitle = (): string => {
    switch (formType) {
      case "trend": return fTitle.trim();
      case "industry": return fName.trim();
      case "stock": return fCode.trim();
    }
  };

  const handleSubmit = async () => {
    const title = getDisplayTitle();
    if (formAction !== "delete" && !title) {
      toast.error(formType === "trend" ? "标题不能为空" : formType === "industry" ? "名称不能为空" : "代码不能为空");
      return;
    }
    setSaving(true);
    try {
      await api.createProposal({
        target_type: formType,
        action: formAction,
        ...(formAction !== "create" && formTargetId ? { target_id: Number(formTargetId) } : {}),
        title: title || `删除目标 #${formTargetId}`,
        confidence: formConfidence,
        payload: buildPayload(),
        source_agent: "manual-test",
      });
      toast.success("提案已创建");
      setMode("view");
      fetchData();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "创建失败";
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  };

  const typeTabs = [
    { label: "全部", value: "" },
    { label: "趋势", value: "trend" },
    { label: "行业", value: "industry" },
    { label: "自选股", value: "stock" },
  ];

  const statusLabel = STATUS_OPTIONS.find((o) => o.value === statusFilter)?.label || "全部状态";
  const dateLabel = sinceDays === 0 ? "全部时间" : `${sinceDays}天内`;

  return (
    <div className="flex h-full flex-col gap-4 p-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">提案</h1>
        <button onClick={startAdd} className="inline-flex items-center gap-1 rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90">
          <PlusCircle className="h-3.5 w-3.5" /> 新建提案
        </button>
      </div>

      {/* Type tabs */}
      <div className="flex gap-1">
        {typeTabs.map((tab) => (
          <button
            key={tab.value}
            onClick={() => setTypeFilter(tab.value)}
            className={cn(
              "rounded-md px-3 py-1 text-xs font-medium transition-colors",
              typeFilter === tab.value
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:bg-muted",
            )}
          >
            {tab.label}
          </button>
        ))}

        <div className="flex-1" />

        {/* Status dropdown */}
        <div className="relative">
          <button
            onClick={(e) => { e.stopPropagation(); setStatusOpen(!statusOpen); setDateOpen(false); }}
            className="inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs text-muted-foreground hover:bg-muted"
          >
            {statusLabel} <ChevronDown className="h-3 w-3" />
          </button>
          {statusOpen && (
            <div className="absolute right-0 top-full z-10 mt-1 w-28 rounded-md border bg-card py-1 shadow-md" onClick={(e) => e.stopPropagation()}>
              <button
                onClick={() => { setStatusFilter(""); setStatusOpen(false); }}
                className={cn("flex w-full items-center px-3 py-1.5 text-xs hover:bg-muted", !statusFilter && "font-medium text-primary")}
              >
                全部状态
              </button>
              {STATUS_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => { setStatusFilter(opt.value); setStatusOpen(false); }}
                  className={cn("flex w-full items-center px-3 py-1.5 text-xs hover:bg-muted", statusFilter === opt.value && "font-medium text-primary")}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Date range dropdown */}
        <div className="relative">
          <button
            onClick={(e) => { e.stopPropagation(); setDateOpen(!dateOpen); setStatusOpen(false); }}
            className="inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs text-muted-foreground hover:bg-muted"
          >
            <Calendar className="h-3 w-3" /> {dateLabel}
          </button>
          {dateOpen && (
            <div className="absolute right-0 top-full z-10 mt-1 w-28 rounded-md border bg-card py-1 shadow-md" onClick={(e) => e.stopPropagation()}>
              {([
                { label: "7天内", days: 7 },
                { label: "30天内", days: 30 },
                { label: "90天内", days: 90 },
                { label: "全部时间", days: 0 },
              ] as const).map((opt) => (
                <button
                  key={opt.days}
                  onClick={() => { setSinceDays(opt.days); setDateOpen(false); }}
                  className={cn("flex w-full items-center px-3 py-1.5 text-xs hover:bg-muted", sinceDays === opt.days && "font-medium text-primary")}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      <MasterDetailLayout
        master={
          <>
            <div className="border-b p-3">
              <SearchInput value={search} onChange={setSearch} />
            </div>
            {filtered.length === 0 ? (
              <EmptyState icon={FileCheck} message="暂无提案" action={{ label: "新建提案", onClick: startAdd }} />
            ) : (
              <CompactList
                items={filtered}
                selectedId={selectedId}
                onSelect={setSelectedId}
                getId={(p) => p.id}
                renderRow={(p) => (
                  <div className="flex flex-col gap-0.5">
                    <div className="flex items-center gap-2">
                      <span className={cn("shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium", ACTION_COLORS[p.action])}>
                        {ACTION_LABELS[p.action]}
                      </span>
                      <StatusDot status={p.status} />
                      <span className="min-w-0 flex-1 truncate">{p.title}</span>
                      <span className="shrink-0 text-[10px] text-muted-foreground">{TYPE_LABELS[p.target_type]}</span>
                      <ConfidenceDot value={p.confidence} />
                    </div>
                    <span className="pl-4 text-[10px] text-muted-foreground">{p.created_at?.slice(0, 10) || ""}</span>
                  </div>
                )}
                actions={() => null}
              />
            )}
          </>
        }
        detail={
          <DetailPanel isEmpty={mode === "view" && !selected}>
            {mode === "add" ? (
              <div className="space-y-4">
                <h2 className="text-base font-semibold">新建提案（测试）</h2>
                <div className="space-y-3">
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="mb-1 block text-xs font-medium text-muted-foreground">目标类型</label>
                      <select value={formType} onChange={(e) => { setFormType(e.target.value as "trend" | "industry" | "stock"); resetForm(); }} className={inputCls}>
                        <option value="trend">趋势</option>
                        <option value="industry">行业</option>
                        <option value="stock">自选股</option>
                      </select>
                    </div>
                    <div>
                      <label className="mb-1 block text-xs font-medium text-muted-foreground">操作类型</label>
                      <select value={formAction} onChange={(e) => setFormAction(e.target.value as "create" | "update" | "delete")} className={inputCls}>
                        <option value="create">新增</option>
                        <option value="update">更新</option>
                        <option value="delete">删除</option>
                      </select>
                    </div>
                  </div>
                  {formAction !== "create" && (
                    <div>
                      <label className="mb-1 block text-xs font-medium text-muted-foreground">目标 ID *</label>
                      <input value={formTargetId} onChange={(e) => setFormTargetId(e.target.value)} className={inputCls} placeholder="update/delete 必填" type="number" />
                    </div>
                  )}
                  {formAction !== "delete" && formType === "trend" && (
                    <>
                      <div>
                        <label className="mb-1 block text-xs font-medium text-muted-foreground">标题 *</label>
                        <input value={fTitle} onChange={(e) => setFTitle(e.target.value)} className={inputCls} placeholder="例如：AI 基础设施轮动" />
                      </div>
                      <div>
                        <label className="mb-1 block text-xs font-medium text-muted-foreground">级别</label>
                        <select value={fLevel} onChange={(e) => setFLevel(e.target.value)} className={inputCls}>
                          {LEVELS.map((l) => <option key={l} value={l}>{LEVEL_LABELS[l]}</option>)}
                        </select>
                      </div>
                      <div>
                        <label className="mb-1 block text-xs font-medium text-muted-foreground">证据</label>
                        <textarea value={fEvidence} onChange={(e) => setFEvidence(e.target.value)} rows={2} className={cn(inputCls, "resize-y")} placeholder="支持证据..." />
                      </div>
                    </>
                  )}
                  {formAction !== "delete" && formType === "industry" && (
                    <>
                      <div>
                        <label className="mb-1 block text-xs font-medium text-muted-foreground">名称 *</label>
                        <input value={fName} onChange={(e) => setFName(e.target.value)} className={inputCls} placeholder="例如：半导体" />
                      </div>
                      <div>
                        <label className="mb-1 block text-xs font-medium text-muted-foreground">原因</label>
                        <textarea value={fReason} onChange={(e) => setFReason(e.target.value)} rows={2} className={cn(inputCls, "resize-y")} placeholder="关注原因..." />
                      </div>
                    </>
                  )}
                  {formAction !== "delete" && formType === "stock" && (
                    <>
                      <div>
                        <label className="mb-1 block text-xs font-medium text-muted-foreground">代码 *</label>
                        <input value={fCode} onChange={(e) => setFCode(e.target.value)} className={inputCls} placeholder="例如：600519" />
                      </div>
                      <div>
                        <label className="mb-1 block text-xs font-medium text-muted-foreground">行业</label>
                        <input value={fIndustryName} onChange={(e) => setFIndustryName(e.target.value)} className={inputCls} placeholder="所属行业" />
                      </div>
                      <div>
                        <label className="mb-1 block text-xs font-medium text-muted-foreground">建议</label>
                        <textarea value={fAdvice} onChange={(e) => setFAdvice(e.target.value)} rows={2} className={cn(inputCls, "resize-y")} placeholder="操作建议..." />
                      </div>
                    </>
                  )}
                  <div>
                    <label className="mb-1 block text-xs font-medium text-muted-foreground">置信度 ({formConfidence})</label>
                    <input type="range" min={0} max={10} value={formConfidence} onChange={(e) => setFormConfidence(Number(e.target.value))} className="w-full accent-primary" />
                  </div>
                </div>
                <div className="flex gap-2">
                  <button onClick={handleSubmit} disabled={saving} className="rounded-md bg-primary px-4 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50">
                    {saving ? "创建中..." : "创建提案"}
                  </button>
                  <button onClick={() => setMode("view")} className="rounded-md border px-4 py-1.5 text-sm hover:bg-muted">取消</button>
                </div>
              </div>
            ) : selected ? (
              <div className="space-y-4">
                <div className="flex items-start justify-between">
                  <h2 className="text-base font-semibold">{selected.title}</h2>
                  <div className="flex gap-1">
                    {selected.status === "pending" && (
                      <>
                        <button onClick={() => handleAdopt(selected.id)} className="rounded-md bg-success/10 px-2 py-1 text-xs font-medium text-success hover:bg-success/20">采纳</button>
                        <button onClick={() => handleReject(selected.id)} className="rounded-md bg-destructive/10 px-2 py-1 text-xs font-medium text-destructive hover:bg-destructive/20">拒绝</button>
                      </>
                    )}
                    <button onClick={() => { setDetailProposal(selected); setDetailOpen(true); }} className="rounded-md border p-1.5 text-muted-foreground hover:bg-muted">
                      <Pencil className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>
                <div className="space-y-2 text-sm">
                  <div className="flex flex-wrap gap-2 text-xs">
                    <span className={cn("rounded px-1.5 py-0.5 font-medium", ACTION_COLORS[selected.action])}>{ACTION_LABELS[selected.action]}</span>
                    <span className="rounded bg-muted px-1.5 py-0.5 text-muted-foreground">{TYPE_LABELS[selected.target_type]}</span>
                    <StatusDot status={selected.status} />
                  </div>
                  <div><span className="text-xs font-medium text-muted-foreground">置信度：</span> <ConfidenceDot value={selected.confidence} /></div>
                  {selected.target_id > 0 && <div><span className="text-xs font-medium text-muted-foreground">目标 ID：</span> {selected.target_id}</div>}
                  {selected.source_agent && <div><span className="text-xs font-medium text-muted-foreground">来源：</span> {selected.source_agent}</div>}
                </div>
                {selected.payload && (
                  <div className="border-t pt-3">
                    <p className="mb-1 text-xs font-medium text-muted-foreground">Payload</p>
                    <pre className="overflow-auto rounded bg-muted/50 p-2 text-xs">{(() => { try { return JSON.stringify(JSON.parse(selected.payload), null, 2); } catch { return selected.payload; } })()}</pre>
                  </div>
                )}
                <div className="border-t pt-3 text-xs text-muted-foreground">
                  <p>创建时间：{selected.created_at || "—"}</p>
                  {selected.reviewed_at && <p>审批时间：{selected.reviewed_at}</p>}
                </div>
              </div>
            ) : null}
          </DetailPanel>
        }
      />

      <ProposalDetailModal
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
        proposal={detailProposal}
        factItem={selected ? (selected as unknown as Record<string, unknown>) : null}
        onAdopt={handleAdopt}
        onReject={handleReject}
      />
    </div>
  );
}
