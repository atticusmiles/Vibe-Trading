import { MasterDetailLayout } from "@/components/fact-tables/MasterDetailLayout";
import { SearchInput } from "@/components/fact-tables/SearchInput";
import { StatusDot } from "@/components/fact-tables/StatusDot";
import { ConfidenceDot } from "@/components/fact-tables/ConfidenceDot";
import { CompactList } from "@/components/fact-tables/CompactList";
import { DetailPanel } from "@/components/fact-tables/DetailPanel";
import { EmptyState } from "@/components/fact-tables/EmptyState";
import { TagInput } from "@/components/fact-tables/TagInput";
import { useDeleteWithUndo } from "@/components/fact-tables/DeleteWithUndo";
import { api, type IndustryItem } from "@/lib/api";
import { PlusCircle, Trash2, Factory, Pencil, ChevronDown } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { useNavigate } from "react-router-dom";

const STATUS_LABELS: Record<string, string> = { proposed: "提议中", adopted: "已采纳", rejected: "已否决", removed: "已移除" };
const inputCls = "w-full rounded-md border bg-background px-3 py-1.5 text-sm outline-none focus:border-primary";
type Mode = "view" | "add" | "edit";

function parseStocks(raw: string | string[]): string[] {
  try { return typeof raw === "string" ? JSON.parse(raw || "[]") : raw; }
  catch { return []; }
}

export function Industries() {
  const navigate = useNavigate();
  const [items, setItems] = useState<IndustryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<string[]>(["proposed", "adopted"]);
  const [filterOpen, setFilterOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [mode, setMode] = useState<Mode>("view");

  const [formName, setFormName] = useState("");
  const [formConfidence, setFormConfidence] = useState(5);
  const [formReason, setFormReason] = useState("");
  const [formReport, setFormReport] = useState("");
  const [formStocks, setFormStocks] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const hash = window.location.hash.replace("#", "");
    if (hash) setSelectedId(Number(hash));
  }, []);

  const selectItem = useCallback((id: number | null) => {
    setSelectedId(id);
    setMode("view");
    navigate(`/industries${id ? `#${id}` : ""}`, { replace: true });
  }, [navigate]);

  const fetchItems = useCallback(async () => {
    try {
      if (statusFilter.length === 0) {
        setItems(await api.listIndustries());
      } else {
        const results = await Promise.all(statusFilter.map((s) => api.listIndustries(s)));
        const seen = new Set<number>();
        const deduped = results.flat().filter((i) => (seen.has(i.id) ? false : seen.add(i.id)));
        setItems(deduped);
      }
    } catch { toast.error("行业加载失败"); }
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
    if (!search) return items;
    const q = search.toLowerCase();
    return items.filter((i) => i.name.toLowerCase().includes(q) || (i.reason || "").toLowerCase().includes(q));
  }, [items, search]);

  const selected = useMemo(() => items.find((i) => i.id === selectedId) ?? null, [items, selectedId]);

  const startAdd = () => {
    setSelectedId(null);
    setFormName(""); setFormConfidence(5); setFormReason(""); setFormReport(""); setFormStocks([]);
    setMode("add");
  };

  const startEdit = () => {
    if (!selected) return;
    setFormName(selected.name);
    setFormConfidence(selected.confidence);
    setFormReason(selected.reason || "");
    setFormReport(selected.research_report || "");
    setFormStocks(parseStocks(selected.recommended_stocks));
    setMode("edit");
  };

  const handleSubmit = async () => {
    if (!formName.trim()) { toast.error("名称不能为空"); return; }
    setSaving(true);
    try {
      if (mode === "add") {
        const created = await api.createIndustry({ name: formName.trim(), confidence: formConfidence, reason: formReason, research_report: formReport, recommended_stocks: formStocks });
        await fetchItems();
        setSelectedId(created.id);
        navigate(`/industries#${created.id}`, { replace: true });
        setMode("view");
        toast.success("行业已创建");
      } else if (mode === "edit" && selectedId) {
        await api.updateIndustry(selectedId, { name: formName.trim(), confidence: formConfidence, reason: formReason, research_report: formReport, recommended_stocks: formStocks } as any);
        await fetchItems();
        setMode("view");
        toast.success("行业已更新");
      }
    } catch { toast.error("保存失败"); }
    finally { setSaving(false); }
  };

  const { performDelete } = useDeleteWithUndo(
    async () => { if (selectedId) await api.deleteIndustry(selectedId); },
    async () => { if (selectedId) { await api.updateIndustry(selectedId, { status: "adopted" } as any); await fetchItems(); } },
    "行业",
  );

  const handleDelete = async () => {
    await performDelete();
    setSelectedId(null); setMode("view");
    navigate("/industries", { replace: true });
    await fetchItems();
  };

  return (
    <div className="flex h-full flex-col gap-4 p-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">行业</h1>
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
              <EmptyState icon={Factory} message="添加第一个行业" action={{ label: "添加行业", onClick: startAdd }} />
            ) : (
              <CompactList
                items={filtered} selectedId={selectedId} onSelect={(id) => selectItem(id)}
                getId={(i) => i.id}
                renderRow={(i) => (
                  <div className="flex items-center gap-2 min-w-0">
                    <StatusDot status={i.status} />
                    <span className="min-w-0 flex-1 truncate">{i.name}</span>
                    <ConfidenceDot value={i.confidence} />
                    {i.recommended_count > 0 && <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 text-[10px]">{i.recommended_count}</span>}
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
                <h2 className="text-base font-semibold">{mode === "add" ? "添加行业" : "编辑行业"}</h2>
                <div className="space-y-3">
                  <div>
                    <label className="mb-1 block text-xs font-medium text-muted-foreground">名称 *</label>
                    <input value={formName} onChange={(e) => setFormName(e.target.value)} className={inputCls} placeholder="例如：半导体" />
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-medium text-muted-foreground">置信度 ({formConfidence})</label>
                    <input type="range" min={0} max={10} value={formConfidence} onChange={(e) => setFormConfidence(Number(e.target.value))} className="w-full accent-primary" />
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-medium text-muted-foreground">原因</label>
                    <textarea value={formReason} onChange={(e) => setFormReason(e.target.value)} rows={3} className={`${inputCls} resize-y`} />
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-medium text-muted-foreground">研究报告</label>
                    <textarea value={formReport} onChange={(e) => setFormReport(e.target.value)} rows={4} className={`${inputCls} resize-y`} />
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-medium text-muted-foreground">推荐股票</label>
                    <TagInput tags={formStocks} onChange={setFormStocks} />
                  </div>
                </div>
                <div className="flex gap-2">
                  <button onClick={handleSubmit} disabled={saving} className="rounded-md bg-primary px-4 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50">
                    {saving ? "保存中..." : mode === "add" ? "创建" : "保存"}
                  </button>
                  <button onClick={() => { setMode("view"); if (!selected) navigate("/industries", { replace: true }); }} className="rounded-md border px-4 py-1.5 text-sm hover:bg-muted">取消</button>
                </div>
              </div>
            ) : selected ? (
              <div className="space-y-4">
                <div className="flex items-start justify-between">
                  <h2 className="text-base font-semibold">{selected.name}</h2>
                  <div className="flex gap-1">
                    <button onClick={startEdit} className="rounded-md border p-1.5 text-muted-foreground hover:bg-muted"><Pencil className="h-3.5 w-3.5" /></button>
                    <button onClick={handleDelete} className="rounded-md border border-destructive/30 p-1.5 text-destructive hover:bg-destructive/10"><Trash2 className="h-3.5 w-3.5" /></button>
                  </div>
                </div>
                <div className="space-y-2 text-sm">
                  <div><span className="text-xs font-medium text-muted-foreground">置信度：</span> <ConfidenceDot value={selected.confidence} /></div>
                  {selected.reason && <div><span className="text-xs font-medium text-muted-foreground">原因：</span><p className="mt-1 whitespace-pre-wrap text-muted-foreground">{selected.reason}</p></div>}
                  {selected.research_report && <div><span className="text-xs font-medium text-muted-foreground">研究报告：</span><p className="mt-1 whitespace-pre-wrap text-muted-foreground">{selected.research_report}</p></div>}
                  {parseStocks(selected.recommended_stocks).length > 0 && (
                    <div>
                      <span className="text-xs font-medium text-muted-foreground">推荐股票：</span>
                      <div className="mt-1 flex flex-wrap gap-1">{parseStocks(selected.recommended_stocks).map((s) => <span key={s} className="rounded bg-muted px-2 py-0.5 text-xs">{s}</span>)}</div>
                    </div>
                  )}
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
