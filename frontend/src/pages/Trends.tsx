import { MasterDetailLayout } from "@/components/fact-tables/MasterDetailLayout";
import { SearchInput } from "@/components/fact-tables/SearchInput";
import { StatusDot } from "@/components/fact-tables/StatusDot";
import { ConfidenceDot } from "@/components/fact-tables/ConfidenceDot";
import { CompactList } from "@/components/fact-tables/CompactList";
import { DetailPanel } from "@/components/fact-tables/DetailPanel";
import { EmptyState } from "@/components/fact-tables/EmptyState";
import { useDeleteWithUndo } from "@/components/fact-tables/DeleteWithUndo";
import { api, type TrendItem } from "@/lib/api";
import { cn } from "@/lib/utils";
import { PlusCircle, Trash2, TrendingUp, Pencil, ChevronDown } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { useNavigate } from "react-router-dom";

const LEVEL_COLORS: Record<string, string> = {
  "long-term": "bg-blue-500/15 text-blue-500",
  "mid-term": "bg-purple-500/15 text-purple-500",
  "short-term": "bg-orange-500/15 text-orange-500",
};
const LEVELS = ["long-term", "mid-term", "short-term"];
const LEVEL_LABELS: Record<string, string> = { "long-term": "长期", "mid-term": "中期", "short-term": "短期" };
const STATUS_LABELS: Record<string, string> = { proposed: "提议中", adopted: "已采纳", rejected: "已否决", removed: "已移除" };
const LEVEL_ORDER: Record<string, number> = { "long-term": 0, "mid-term": 1, "short-term": 2 };
const inputCls = "w-full rounded-md border bg-background px-3 py-1.5 text-sm outline-none focus:border-primary";

type Mode = "view" | "add" | "edit";

function fmtDate(iso: string | null): string {
  if (!iso) return "";
  return iso.slice(0, 10);
}

export function Trends() {
  const navigate = useNavigate();
  const [items, setItems] = useState<TrendItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<string[]>(["proposed", "adopted"]);
  const [filterOpen, setFilterOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [mode, setMode] = useState<Mode>("view");

  // Form state
  const [formTitle, setFormTitle] = useState("");
  const [formLevel, setFormLevel] = useState("mid-term");
  const [formConfidence, setFormConfidence] = useState(5);
  const [formEvidence, setFormEvidence] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const hash = window.location.hash.replace("#", "");
    if (hash) setSelectedId(Number(hash));
  }, []);

  const selectItem = useCallback((id: number | null) => {
    setSelectedId(id);
    setMode("view");
    navigate(`/trends${id ? `#${id}` : ""}`, { replace: true });
  }, [navigate]);

  const fetchItems = useCallback(async () => {
    try {
      if (statusFilter.length === 0) {
        setItems(await api.listTrends());
      } else {
        const results = await Promise.all(statusFilter.map((s) => api.listTrends(s)));
        const seen = new Set<number>();
        const deduped = results.flat().filter((i) => (seen.has(i.id) ? false : seen.add(i.id)));
        setItems(deduped);
      }
    } catch { toast.error("趋势加载失败"); }
    finally { setLoading(false); }
  }, [statusFilter]);

  useEffect(() => { fetchItems(); }, [fetchItems]);

  useEffect(() => {
    if (!filterOpen) return;
    const close = () => setFilterOpen(false);
    document.addEventListener("click", close);
    return () => document.removeEventListener("click", close);
  }, [filterOpen]);

  const filtered = useMemo(() => {
    const list = search
      ? items.filter((i) => i.title.toLowerCase().includes(search.toLowerCase()) || (i.evidence || "").toLowerCase().includes(search.toLowerCase()))
      : items;
    return [...list].sort((a, b) => {
      const la = LEVEL_ORDER[a.level || ""] ?? 9;
      const lb = LEVEL_ORDER[b.level || ""] ?? 9;
      if (la !== lb) return la - lb;
      return b.confidence - a.confidence;
    });
  }, [items, search]);

  const selected = useMemo(() => items.find((i) => i.id === selectedId) ?? null, [items, selectedId]);

  const startAdd = () => {
    setSelectedId(null);
    setFormTitle(""); setFormLevel("mid-term"); setFormConfidence(5); setFormEvidence("");
    setMode("add");
  };

  const startEdit = () => {
    if (!selected) return;
    setFormTitle(selected.title);
    setFormLevel(selected.level || "mid-term");
    setFormConfidence(selected.confidence);
    setFormEvidence(selected.evidence || "");
    setMode("edit");
  };

  const handleSubmit = async () => {
    if (!formTitle.trim()) { toast.error("标题不能为空"); return; }
    setSaving(true);
    try {
      if (mode === "add") {
        const created = await api.createTrend({ title: formTitle.trim(), level: formLevel, confidence: formConfidence, evidence: formEvidence });
        await fetchItems();
        setSelectedId(created.id);
        navigate(`/trends#${created.id}`, { replace: true });
        setMode("view");
        toast.success("趋势已创建");
      } else if (mode === "edit" && selectedId) {
        await api.updateTrend(selectedId, { title: formTitle.trim(), level: formLevel, confidence: formConfidence, evidence: formEvidence });
        await fetchItems();
        setMode("view");
        toast.success("趋势已更新");
      }
    } catch { toast.error("保存失败"); }
    finally { setSaving(false); }
  };

  const { performDelete } = useDeleteWithUndo(
    async () => { if (selectedId) await api.deleteTrend(selectedId); },
    async () => { if (selectedId) { await api.updateTrend(selectedId, { status: "adopted" }); await fetchItems(); } },
    "趋势",
  );

  const handleDelete = async () => {
    await performDelete();
    setSelectedId(null);
    setMode("view");
    navigate("/trends", { replace: true });
    await fetchItems();
  };

  return (
    <div className="flex h-full flex-col gap-4 p-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">趋势</h1>
        <button onClick={startAdd} className="inline-flex items-center gap-1 rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90">
          <PlusCircle className="h-3.5 w-3.5" /> 添加
        </button>
      </div>

      <MasterDetailLayout
        master={
          <>
            <div className="flex items-center gap-2 border-b p-3">
              <div className="flex-1">
                <SearchInput value={search} onChange={setSearch} />
              </div>
              <div className="relative">
                <button onClick={(e) => { e.stopPropagation(); setFilterOpen(!filterOpen); }} className="inline-flex items-center gap-1 rounded-md border px-2 py-1.5 text-xs text-muted-foreground hover:bg-muted">
                  {statusFilter.length === 0 ? "筛选" : `${statusFilter.length} 个筛选`} <ChevronDown className="h-3 w-3" />
                </button>
                {filterOpen && (
                  <div className="absolute right-0 top-full z-10 mt-1 w-36 rounded-md border bg-card py-1 shadow-md" onClick={(e) => e.stopPropagation()}>
                    {([
                      ["提议中", "proposed"],
                      ["已采纳", "adopted"],
                      ["已否决", "rejected"],
                      ["已移除", "removed"],
                    ] as const).map(([label, val]) => (
                      <label key={val} className="flex cursor-pointer items-center gap-2 px-3 py-1 text-xs hover:bg-muted">
                        <input
                          type="checkbox" checked={statusFilter.includes(val)}
                          onChange={() => {
                            setStatusFilter((prev) =>
                              prev.includes(val) ? prev.filter((s) => s !== val) : [...prev, val]
                            );
                          }}
                          className="h-3 w-3 accent-primary"
                        />
                        {label}
                      </label>
                    ))}
                  </div>
                )}
              </div>
            </div>
            {filtered.length === 0 ? (
              <EmptyState icon={TrendingUp} message="添加第一个趋势" action={{ label: "添加趋势", onClick: startAdd }} />
            ) : (
              <CompactList
                items={filtered} selectedId={selectedId} onSelect={(id) => selectItem(id)}
                getId={(i) => i.id}
                renderRow={(i) => (
                  <div className="flex flex-col gap-0.5">
                    <div className="flex items-center gap-2">
                      <StatusDot status={i.status} />
                      <span className="min-w-0 flex-1 truncate">{i.title}</span>
                      {i.level && <span className={cn("shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium", LEVEL_COLORS[i.level] || "")}>{LEVEL_LABELS[i.level] || i.level}</span>}
                      <ConfidenceDot value={i.confidence} />
                    </div>
                    {i.updated_at && <span className="pl-4 text-[10px] text-muted-foreground">{fmtDate(i.updated_at)}</span>}
                  </div>
                )}
                actions={(i) => (
                  <button onClick={(e) => { e.stopPropagation(); setSelectedId(i.id); handleDelete(); }} className="p-1 text-muted-foreground hover:text-destructive">
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                )}
              />
            )}
          </>
        }
        detail={
          <DetailPanel isEmpty={mode === "view" && !selected}>
            {(mode === "add" || mode === "edit") ? (
              <div className="space-y-4">
                <h2 className="text-base font-semibold">{mode === "add" ? "添加趋势" : "编辑趋势"}</h2>
                <div className="space-y-3">
                  <div>
                    <label className="mb-1 block text-xs font-medium text-muted-foreground">标题 *</label>
                    <input value={formTitle} onChange={(e) => setFormTitle(e.target.value)} className={inputCls} placeholder="例如：AI 基础设施轮动" />
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-medium text-muted-foreground">级别</label>
                    <select value={formLevel} onChange={(e) => setFormLevel(e.target.value)} className={inputCls}>
                      {LEVELS.map((l) => <option key={l} value={l}>{LEVEL_LABELS[l]}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-medium text-muted-foreground">置信度 ({formConfidence})</label>
                    <input type="range" min={0} max={10} value={formConfidence} onChange={(e) => setFormConfidence(Number(e.target.value))} className="w-full accent-primary" />
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-medium text-muted-foreground">证据</label>
                    <textarea value={formEvidence} onChange={(e) => setFormEvidence(e.target.value)} rows={3} className={cn(inputCls, "resize-y")} placeholder="支持证据..." />
                  </div>
                </div>
                <div className="flex gap-2">
                  <button onClick={handleSubmit} disabled={saving} className="rounded-md bg-primary px-4 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50">
                    {saving ? "保存中..." : mode === "add" ? "创建" : "保存"}
                  </button>
                  <button onClick={() => { setMode(selected ? "view" : "view"); if (!selected) navigate("/trends", { replace: true }); }} className="rounded-md border px-4 py-1.5 text-sm hover:bg-muted">
                    取消
                  </button>
                </div>
              </div>
            ) : selected ? (
              <div className="space-y-4">
                <div className="flex items-start justify-between">
                  <h2 className="text-base font-semibold">{selected.title}</h2>
                  <div className="flex gap-1">
                    <button onClick={startEdit} className="rounded-md border p-1.5 text-muted-foreground hover:bg-muted"><Pencil className="h-3.5 w-3.5" /></button>
                    <button onClick={handleDelete} className="rounded-md border border-destructive/30 p-1.5 text-destructive hover:bg-destructive/10"><Trash2 className="h-3.5 w-3.5" /></button>
                  </div>
                </div>
                <div className="space-y-2 text-sm">
                  {selected.level && <div><span className="text-xs font-medium text-muted-foreground">级别：</span> <span className={cn("ml-2 rounded px-1.5 py-0.5 text-xs font-medium", LEVEL_COLORS[selected.level])}>{LEVEL_LABELS[selected.level] || selected.level}</span></div>}
                  <div><span className="text-xs font-medium text-muted-foreground">置信度：</span> <ConfidenceDot value={selected.confidence} /></div>
                  {selected.evidence && <div><span className="text-xs font-medium text-muted-foreground">证据：</span><p className="mt-1 whitespace-pre-wrap text-muted-foreground">{selected.evidence}</p></div>}
                </div>
                <div className="border-t pt-3 text-xs text-muted-foreground">
                  <p>状态：{STATUS_LABELS[selected.status] || selected.status}</p>
                  {selected.created_at && <p>创建时间：{selected.created_at}</p>}
                  {selected.updated_at && <p>更新时间：{selected.updated_at}</p>}
                </div>
              </div>
            ) : null}
          </DetailPanel>
        }
      />
    </div>
  );
}
