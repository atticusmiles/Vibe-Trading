import { MasterDetailLayout } from "@/components/fact-tables/MasterDetailLayout";
import { SearchInput } from "@/components/fact-tables/SearchInput";
import { StatusDot } from "@/components/fact-tables/StatusDot";
import { ConfidenceDot } from "@/components/fact-tables/ConfidenceDot";
import { CompactList } from "@/components/fact-tables/CompactList";
import { DetailPanel } from "@/components/fact-tables/DetailPanel";
import { EmptyState } from "@/components/fact-tables/EmptyState";
import { useDeleteWithUndo } from "@/components/fact-tables/DeleteWithUndo";
import { api, type StockItem } from "@/lib/api";
import { cn } from "@/lib/utils";
import { CandlestickChart, PlusCircle, Trash2, Pencil, ChevronDown } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { useNavigate } from "react-router-dom";

const ADVICE_COLORS: Record<string, string> = { buy: "text-success", sell: "text-destructive", hold: "text-muted-foreground" };
const ADVICE_LABELS: Record<string, string> = { buy: "买入", sell: "卖出", hold: "持有" };
const STATUS_LABELS: Record<string, string> = { proposed: "提议中", adopted: "已采纳", rejected: "已否决", removed: "已移除" };
const inputCls = "w-full rounded-md border bg-background px-3 py-1.5 text-sm outline-none focus:border-primary";
type Mode = "view" | "add" | "edit";

export function Stocks() {
  const navigate = useNavigate();
  const [items, setItems] = useState<StockItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<string[]>(["proposed", "adopted"]);
  const [filterOpen, setFilterOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [mode, setMode] = useState<Mode>("view");

  const [formName, setFormName] = useState("");
  const [formCode, setFormCode] = useState("");
  const [formIndustry, setFormIndustry] = useState("");
  const [formConfidence, setFormConfidence] = useState(5);
  const [formAdvice, setFormAdvice] = useState("");
  const [formTarget, setFormTarget] = useState("");
  const [formStop, setFormStop] = useState("");
  const [formPosition, setFormPosition] = useState("");
  const [formReason, setFormReason] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const hash = window.location.hash.replace("#", "");
    if (hash) setSelectedId(Number(hash));
  }, []);

  const selectItem = useCallback((id: number | null) => {
    setSelectedId(id);
    setMode("view");
    navigate(`/stocks${id ? `#${id}` : ""}`, { replace: true });
  }, [navigate]);

  const fetchItems = useCallback(async () => {
    try {
      if (statusFilter.length === 0) {
        setItems(await api.listStocks());
      } else {
        const results = await Promise.all(statusFilter.map((s) => api.listStocks(s)));
        const seen = new Set<number>();
        const deduped = results.flat().filter((i) => (seen.has(i.id) ? false : seen.add(i.id)));
        setItems(deduped);
      }
    } catch { toast.error("自选股加载失败"); }
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
    return items.filter((i) => i.name.toLowerCase().includes(q) || i.code.toLowerCase().includes(q) || (i.industry_name || "").toLowerCase().includes(q));
  }, [items, search]);

  const selected = useMemo(() => items.find((i) => i.id === selectedId) ?? null, [items, selectedId]);

  const startAdd = () => {
    setSelectedId(null);
    setFormName(""); setFormCode(""); setFormIndustry(""); setFormConfidence(5);
    setFormAdvice(""); setFormTarget(""); setFormStop(""); setFormPosition(""); setFormReason("");
    setMode("add");
  };

  const startEdit = () => {
    if (!selected) return;
    setFormName(selected.name);
    setFormCode(selected.code);
    setFormIndustry(selected.industry_name || "");
    setFormConfidence(selected.confidence);
    setFormAdvice(selected.advice || "");
    setFormTarget(selected.target_price != null ? String(selected.target_price) : "");
    setFormStop(selected.stop_loss != null ? String(selected.stop_loss) : "");
    setFormPosition(selected.position != null ? String(selected.position) : "");
    setFormReason(selected.reason || "");
    setMode("edit");
  };

  const handleSubmit = async () => {
    if (!formName.trim() || !formCode.trim()) { toast.error("名称和代码不能为空"); return; }
    setSaving(true);
    try {
      const payload = {
        name: formName.trim(), code: formCode.trim(), industry_name: formIndustry || undefined,
        confidence: formConfidence, advice: formAdvice || undefined,
        target_price: formTarget ? Number(formTarget) : undefined,
        stop_loss: formStop ? Number(formStop) : undefined,
        position: formPosition ? Number(formPosition) : undefined,
        reason: formReason || undefined,
      };
      if (mode === "add") {
        const created = await api.createStock(payload);
        await fetchItems();
        setSelectedId(created.id);
        navigate(`/stocks#${created.id}`, { replace: true });
        setMode("view");
        toast.success("自选股已创建");
      } else if (mode === "edit" && selectedId) {
        await api.updateStock(selectedId, payload as any);
        await fetchItems();
        setMode("view");
        toast.success("自选股已更新");
      }
    } catch { toast.error("保存失败"); }
    finally { setSaving(false); }
  };

  const { performDelete } = useDeleteWithUndo(
    async () => { if (selectedId) await api.deleteStock(selectedId); },
    async () => { if (selectedId) { await api.updateStock(selectedId, { status: "adopted" } as any); await fetchItems(); } },
    "自选股",
  );

  const handleDelete = async () => {
    await performDelete();
    setSelectedId(null); setMode("view");
    navigate("/stocks", { replace: true });
    await fetchItems();
  };

  return (
    <div className="flex h-full flex-col gap-4 p-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">自选股</h1>
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
              <EmptyState icon={CandlestickChart} message="添加第一只自选股" action={{ label: "添加自选股", onClick: startAdd }} />
            ) : (
              <CompactList
                items={filtered} selectedId={selectedId} onSelect={(id) => selectItem(id)}
                getId={(i) => i.id}
                renderRow={(i) => (
                  <div className="flex items-center gap-2 min-w-0">
                    <StatusDot status={i.status} />
                    <span className="min-w-0 flex-1 truncate font-medium">{i.name}</span>
                    <span className="shrink-0 text-xs text-muted-foreground">{i.code}</span>
                    {i.advice && <span className={cn("shrink-0 text-[10px] font-medium", ADVICE_COLORS[i.advice.toLowerCase()] || "text-muted-foreground")}>{ADVICE_LABELS[i.advice.toLowerCase()] || i.advice}</span>}
                    <ConfidenceDot value={i.confidence} />
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
                <h2 className="text-base font-semibold">{mode === "add" ? "添加自选股" : "编辑自选股"}</h2>
                <div className="space-y-3">
                  <div className="grid gap-3 sm:grid-cols-2">
                    <div>
                      <label className="mb-1 block text-xs font-medium text-muted-foreground">名称 *</label>
                      <input value={formName} onChange={(e) => setFormName(e.target.value)} className={inputCls} placeholder="例如：贵州茅台" />
                    </div>
                    <div>
                      <label className="mb-1 block text-xs font-medium text-muted-foreground">代码 *</label>
                      <input value={formCode} onChange={(e) => setFormCode(e.target.value)} className={inputCls} placeholder="例如：600519.SH" />
                    </div>
                  </div>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <div>
                      <label className="mb-1 block text-xs font-medium text-muted-foreground">行业</label>
                      <input value={formIndustry} onChange={(e) => setFormIndustry(e.target.value)} className={inputCls} placeholder="例如：消费" />
                    </div>
                    <div>
                      <label className="mb-1 block text-xs font-medium text-muted-foreground">建议</label>
                      <input value={formAdvice} onChange={(e) => setFormAdvice(e.target.value)} className={inputCls} placeholder="例如：买入、持有、卖出" />
                    </div>
                  </div>
                  <div className="grid gap-3 sm:grid-cols-3">
                    <div>
                      <label className="mb-1 block text-xs font-medium text-muted-foreground">目标价</label>
                      <input type="number" value={formTarget} onChange={(e) => setFormTarget(e.target.value)} className={inputCls} placeholder="0.00" />
                    </div>
                    <div>
                      <label className="mb-1 block text-xs font-medium text-muted-foreground">止损价</label>
                      <input type="number" value={formStop} onChange={(e) => setFormStop(e.target.value)} className={inputCls} placeholder="0.00" />
                    </div>
                    <div>
                      <label className="mb-1 block text-xs font-medium text-muted-foreground">仓位</label>
                      <input type="number" value={formPosition} onChange={(e) => setFormPosition(e.target.value)} className={inputCls} placeholder="0" />
                    </div>
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-medium text-muted-foreground">置信度 ({formConfidence})</label>
                    <input type="range" min={0} max={10} value={formConfidence} onChange={(e) => setFormConfidence(Number(e.target.value))} className="w-full accent-primary" />
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-medium text-muted-foreground">原因</label>
                    <textarea value={formReason} onChange={(e) => setFormReason(e.target.value)} rows={3} className={`${inputCls} resize-y`} />
                  </div>
                </div>
                <div className="flex gap-2">
                  <button onClick={handleSubmit} disabled={saving} className="rounded-md bg-primary px-4 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50">
                    {saving ? "保存中..." : mode === "add" ? "创建" : "保存"}
                  </button>
                  <button onClick={() => { setMode("view"); if (!selected) navigate("/stocks", { replace: true }); }} className="rounded-md border px-4 py-1.5 text-sm hover:bg-muted">取消</button>
                </div>
              </div>
            ) : selected ? (
              <div className="space-y-4">
                <div className="flex items-start justify-between">
                  <div>
                    <h2 className="text-base font-semibold">{selected.name}</h2>
                    <p className="font-mono text-xs text-muted-foreground">{selected.code}</p>
                  </div>
                  <div className="flex gap-1">
                    <button onClick={startEdit} className="rounded-md border p-1.5 text-muted-foreground hover:bg-muted"><Pencil className="h-3.5 w-3.5" /></button>
                    <button onClick={handleDelete} className="rounded-md border border-destructive/30 p-1.5 text-destructive hover:bg-destructive/10"><Trash2 className="h-3.5 w-3.5" /></button>
                  </div>
                </div>
                <div className="space-y-2 text-sm">
                  {selected.industry_name && <div><span className="text-xs font-medium text-muted-foreground">行业：</span> <span className="ml-1">{selected.industry_name}</span></div>}
                  {selected.advice && <div><span className="text-xs font-medium text-muted-foreground">建议：</span> <span className={cn("ml-1 font-medium", ADVICE_COLORS[selected.advice.toLowerCase()])}>{ADVICE_LABELS[selected.advice.toLowerCase()] || selected.advice}</span></div>}
                  <div className="grid grid-cols-3 gap-2">
                    {selected.target_price != null && <div><span className="text-xs text-muted-foreground">目标价：</span> <span className="ml-1">{selected.target_price}</span></div>}
                    {selected.stop_loss != null && <div><span className="text-xs text-muted-foreground">止损价：</span> <span className="ml-1">{selected.stop_loss}</span></div>}
                    {selected.position != null && <div><span className="text-xs text-muted-foreground">仓位：</span> <span className="ml-1">{selected.position}</span></div>}
                  </div>
                  <div><span className="text-xs font-medium text-muted-foreground">置信度：</span> <ConfidenceDot value={selected.confidence} /></div>
                  {selected.reason && <div><span className="text-xs font-medium text-muted-foreground">原因：</span><p className="mt-1 whitespace-pre-wrap text-muted-foreground">{selected.reason}</p></div>}
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
