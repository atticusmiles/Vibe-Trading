import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { Database, KeyRound, Loader2, Lock, RotateCcw, Save, Server, SlidersHorizontal, Wrench, Briefcase } from "lucide-react";
import { toast } from "sonner";
import { api, isAuthRequiredError } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

const fieldClass =
  "w-full rounded-md border bg-background px-3 py-2 text-sm outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/20 disabled:cursor-not-allowed disabled:opacity-60";
const labelClass = "text-sm font-medium";
const hintClass = "text-xs text-muted-foreground";

const TABS = ["llm", "preferences", "system", "security"] as const;
type TabKey = (typeof TABS)[number];

const tabMeta: Record<TabKey, { label: string; icon: typeof Server; sections: { id: string; label: string }[] }> = {
  llm: {
    label: "LLM & Data",
    icon: Server,
    sections: [
      { id: "llm-config", label: "LLM Configuration" },
      { id: "generation", label: "Generation Parameters" },
      { id: "data-sources", label: "Data Sources" },
    ],
  },
  preferences: {
    label: "Investment Preferences",
    icon: Briefcase,
    sections: [
      { id: "invest-style", label: "Investment Style" },
      { id: "markets", label: "Markets & Industries" },
      { id: "capital", label: "Capital & Strategy" },
    ],
  },
  system: {
    label: "System Settings",
    icon: Wrench,
    sections: [
      { id: "scheduler", label: "Scheduler" },
      { id: "proposals", label: "Proposal Limits" },
    ],
  },
  security: {
    label: "Security",
    icon: Lock,
    sections: [
      { id: "password", label: "Change Password" },
    ],
  },
};

// ===== Shared: Section nav =====
function SectionNav({ sections, activeId }: { sections: { id: string; label: string }[]; activeId: string }) {
  return (
    <nav className="space-y-1 text-sm">
      {sections.map((s) => (
        <a
          key={s.id}
          href={`#${s.id}`}
          onClick={(e) => {
            e.preventDefault();
            document.getElementById(s.id)?.scrollIntoView({ behavior: "smooth", block: "start" });
          }}
          className={`block rounded-md px-3 py-1.5 transition-colors ${
            activeId === s.id
              ? "bg-primary/10 text-primary font-medium"
              : "text-muted-foreground hover:bg-muted hover:text-foreground"
          }`}
        >
          {s.label}
        </a>
      ))}
    </nav>
  );
}

function useActiveSection(ids: string[]) {
  const [active, setActive] = useState(ids[0] || "");
  useEffect(() => {
    const visible = new Set<string>();
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) visible.add(entry.target.id);
          else visible.delete(entry.target.id);
        }
        const first = ids.find((id) => visible.has(id));
        if (first) setActive(first);
      },
      { rootMargin: "-80px 0px -60% 0px" },
    );
    for (const id of ids) {
      const el = document.getElementById(id);
      if (el) observer.observe(el);
    }
    return () => observer.disconnect();
  }, [ids]);
  return active;
}

function useCtrlS(handler: () => void) {
  const ref = useRef(handler);
  ref.current = handler;
  useEffect(() => {
    const listener = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "s") { e.preventDefault(); ref.current(); }
    };
    window.addEventListener("keydown", listener);
    return () => window.removeEventListener("keydown", listener);
  }, []);
}

// ===== Save / Reset buttons for right-side nav =====
function ActionBar({ saving, onSave, onReset }: { saving: boolean; onSave: () => void; onReset: () => void }) {
  return (
    <div className="mt-4 flex flex-col gap-2">
      <button
        type="button"
        onClick={onSave}
        disabled={saving}
        className="inline-flex w-full items-center justify-center gap-1.5 rounded-md bg-primary px-4 py-1.5 text-sm font-medium text-primary-foreground transition hover:opacity-90 disabled:opacity-50"
      >
        {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
        Save
      </button>
      <button
        type="button"
        onClick={onReset}
        className="inline-flex w-full items-center justify-center gap-1.5 rounded-md border px-3 py-1.5 text-sm text-muted-foreground transition hover:bg-muted hover:text-foreground"
      >
        <RotateCcw className="h-3.5 w-3.5" />
        Reset
      </button>
    </div>
  );
}

// ===== LLM & Data Page =====
function LLMDataPage() {
  const { t } = useI18n();
  const [data, setData] = useState<Record<string, any>>({});
  const [snapshot, setSnapshot] = useState<Record<string, any>>({});
  const [apiKey, setApiKey] = useState("");
  const [clearApiKey, setClearApiKey] = useState(false);
  const [tushareToken, setTushareToken] = useState("");
  const [clearTushare, setClearTushare] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const sections = tabMeta.llm.sections;
  const activeId = useActiveSection(sections.map((s) => s.id));

  useEffect(() => {
    api.getApiKeys()
      .then((d) => { setData(d); setSnapshot(JSON.parse(JSON.stringify(d))); })
      .catch((err) => { if (isAuthRequiredError(err)) toast.error(err.message); })
      .finally(() => setLoading(false));
  }, []);

  const llm = data.llm_provider || {} as any;
  const gen = data.generation || {} as any;

  const updateLlm = (patch: Record<string, any>) => setData({ ...data, llm_provider: { ...llm, ...patch } });
  const updateGen = (patch: Record<string, any>) => setData({ ...data, generation: { ...gen, ...patch } });

  const save = async () => {
    setSaving(true);
    try {
      const payload = JSON.parse(JSON.stringify(data));
      // Handle API key changes
      if (clearApiKey) {
        payload.llm_provider = { ...payload.llm_provider, key: "" };
      } else if (apiKey.trim()) {
        payload.llm_provider = { ...payload.llm_provider, key: apiKey.trim() };
      }
      // Handle tushare changes
      if (clearTushare) {
        payload.tushare = { ...(payload.tushare || {}), key: "" };
      } else if (tushareToken.trim()) {
        payload.tushare = { ...(payload.tushare || {}), key: tushareToken.trim() };
      }
      await api.updateApiKeys(payload);
      setData(payload);
      setSnapshot(JSON.parse(JSON.stringify(payload)));
      setApiKey("");
      setClearApiKey(false);
      setTushareToken("");
      setClearTushare(false);
      toast.success("Settings saved");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const reset = () => {
    setData(JSON.parse(JSON.stringify(snapshot)));
    setApiKey("");
    setClearApiKey(false);
    setTushareToken("");
    setClearTushare(false);
  };

  useCtrlS(save);

  if (loading) return <div className="flex items-center gap-2 p-12 text-muted-foreground"><Loader2 className="h-5 w-5 animate-spin" /> Loading...</div>;

  const apiKeyConfigured = !!(llm.key && llm.key.trim());
  const tushareConfigured = !!((data.tushare || {}).key || "").trim();

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_180px]">
      <div className="space-y-6">
          {/* LLM Config */}
          <section id="llm-config" className="rounded-lg border bg-card p-5 shadow-sm scroll-mt-20">
            <div className="mb-4 flex items-center gap-2">
              <Server className="h-4 w-4 text-primary" />
              <h2 className="text-base font-semibold">LLM Configuration</h2>
            </div>
            <div className="grid gap-4 ">
              <label className="grid gap-1">
                <span className={labelClass}>Base URL</span>
                <input value={llm.base_url || ""} onChange={(e) => updateLlm({ base_url: e.target.value })} className={fieldClass} placeholder="https://open.bigmodel.cn/api/coding/paas/v4" />
              </label>
              <label className="grid gap-1">
                <span className={labelClass}>Model</span>
                <input value={llm.model || ""} onChange={(e) => updateLlm({ model: e.target.value })} className={fieldClass} required placeholder="glm-5.1" />
              </label>
              <label className="grid gap-1">
                <span className={labelClass}>API Key</span>
                <div className="relative">
                  <KeyRound className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
                  <input type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} className={`${fieldClass} pl-9`} placeholder={apiKeyConfigured ? "API key configured" : "Enter API key"} disabled={clearApiKey} />
                </div>
                <label className="flex items-center gap-2 text-xs text-muted-foreground">
                  <input type="checkbox" checked={clearApiKey} onChange={(e) => { setClearApiKey(e.target.checked); if (e.target.checked) setApiKey(""); }} className="h-3.5 w-3.5 accent-primary" />
                  Clear saved key
                </label>
              </label>
            </div>
          </section>

          {/* Generation */}
          <section id="generation" className="rounded-lg border bg-card p-5 shadow-sm scroll-mt-20">
            <div className="mb-4 flex items-center gap-2">
              <SlidersHorizontal className="h-4 w-4 text-primary" />
              <h2 className="text-base font-semibold">Generation Parameters</h2>
            </div>
            <div className="grid gap-4 sm:grid-cols-2 ">
              <label className="grid gap-1">
                <span className={labelClass}>Temperature</span>
                <input type="number" min={0} max={2} step={0.1} value={gen.temperature ?? 0} onChange={(e) => updateGen({ temperature: Number(e.target.value) })} className={fieldClass} />
              </label>
              <label className="grid gap-1">
                <span className={labelClass}>Timeout (s)</span>
                <input type="number" min={1} max={3600} value={gen.timeout_seconds ?? 120} onChange={(e) => updateGen({ timeout_seconds: Number(e.target.value) })} className={fieldClass} />
              </label>
              <label className="grid gap-1">
                <span className={labelClass}>Max Retries</span>
                <input type="number" min={0} max={20} value={gen.max_retries ?? 2} onChange={(e) => updateGen({ max_retries: Number(e.target.value) })} className={fieldClass} />
              </label>
              <label className="grid gap-1">
                <span className={labelClass}>Reasoning Effort</span>
                <select value={gen.reasoning_effort || ""} onChange={(e) => updateGen({ reasoning_effort: e.target.value })} className={fieldClass}>
                  <option value="">Off</option>
                  <option value="low">low</option>
                  <option value="medium">medium</option>
                  <option value="high">high</option>
                  <option value="max">max</option>
                </select>
              </label>
            </div>
          </section>

          {/* Data Sources */}
          <section id="data-sources" className="rounded-lg border bg-card p-5 shadow-sm scroll-mt-20">
            <div className="mb-4 flex items-center gap-2">
              <Database className="h-4 w-4 text-primary" />
              <h2 className="text-base font-semibold">Data Sources</h2>
            </div>
            <div className="grid gap-4 ">
              <label className="grid gap-1">
                <span className={labelClass}>Tushare Token</span>
                <div className="relative">
                  <KeyRound className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
                  <input type="password" value={tushareToken} onChange={(e) => setTushareToken(e.target.value)} className={`${fieldClass} pl-9`} placeholder={tushareConfigured ? "Token configured" : "Enter token"} disabled={clearTushare} />
                </div>
                <label className="flex items-center gap-2 text-xs text-muted-foreground">
                  <input type="checkbox" checked={clearTushare} onChange={(e) => { setClearTushare(e.target.checked); if (e.target.checked) setTushareToken(""); }} className="h-3.5 w-3.5 accent-primary" />
                  Clear saved token
                </label>
              </label>
            </div>
          </section>
        </div>

        {/* Right nav + actions */}
        <aside className="hidden lg:block self-start sticky top-36">
          <h3 className="mb-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">Sections</h3>
          <SectionNav sections={sections} activeId={activeId} />
          <ActionBar saving={saving} onSave={save} onReset={reset} />
        </aside>
      </div>
  );
}

// ===== Preferences Page =====
const INVESTMENT_STYLES = ["价值投资", "成长投资", "指数投资", "量化交易"];
const RISK_APPETITES = ["保守型", "稳健型", "激进型"];
const FOCUS_MARKETS = ["A股", "港股", "美股"];
const FOCUS_INDUSTRIES = ["科技", "消费", "医药", "金融", "能源", "制造业", "房地产", "公用事业"];
const HOLDING_PERIODS = ["短线", "中线", "长线"];
const CAPITAL_SCALES = ["10万以下", "10~50万", "50~100万", "100万以上"];

function PreferencesPage() {
  const [data, setData] = useState<Record<string, any>>({});
  const [snapshot, setSnapshot] = useState<Record<string, any>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const sections = tabMeta.preferences.sections;
  const activeId = useActiveSection(sections.map((s) => s.id));

  useEffect(() => {
    api.getPreferences()
      .then((d) => { setData(d); setSnapshot(JSON.parse(JSON.stringify(d))); })
      .catch((err) => toast.error(err.message))
      .finally(() => setLoading(false));
  }, []);

  const save = async () => {
    setSaving(true);
    try {
      await api.updatePreferences(data);
      setSnapshot(JSON.parse(JSON.stringify(data)));
      toast.success("Preferences saved");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const reset = () => setData({ ...snapshot });

  useCtrlS(save);

  function toggleArray(field: string, value: string) {
    const arr: string[] = data[field] || [];
    setData({ ...data, [field]: arr.includes(value) ? arr.filter((v) => v !== value) : [...arr, value] });
  }

  function CheckboxGroup({ field, options }: { field: string; options: string[] }) {
    const selected: string[] = data[field] || [];
    return (
      <div className="flex flex-wrap gap-2">
        {options.map((opt) => (
          <label key={opt} className="flex items-center gap-1.5 text-sm">
            <input type="checkbox" checked={selected.includes(opt)} onChange={() => toggleArray(field, opt)} className="h-3.5 w-3.5 accent-primary" />
            {opt}
          </label>
        ))}
      </div>
    );
  }

  if (loading) return <div className="flex items-center gap-2 p-12 text-muted-foreground"><Loader2 className="h-5 w-5 animate-spin" /> Loading...</div>;

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_180px]">
      <div className="space-y-6">
          <section id="invest-style" className="rounded-lg border bg-card p-5 shadow-sm scroll-mt-20">
            <h2 className="mb-4 text-base font-semibold">Investment Style</h2>
            <div className="grid gap-4 sm:grid-cols-2 ">
              <label className="grid gap-1">
                <span className={labelClass}>Style</span>
                <select className={fieldClass} value={data.investment_style || ""} onChange={(e) => setData({ ...data, investment_style: e.target.value })}>
                  <option value="">Select...</option>
                  {INVESTMENT_STYLES.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              </label>
              <label className="grid gap-1">
                <span className={labelClass}>Risk Appetite</span>
                <select className={fieldClass} value={data.risk_appetite || ""} onChange={(e) => setData({ ...data, risk_appetite: e.target.value })}>
                  <option value="">Select...</option>
                  {RISK_APPETITES.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              </label>
            </div>
          </section>

          <section id="markets" className="rounded-lg border bg-card p-5 shadow-sm scroll-mt-20">
            <h2 className="mb-4 text-base font-semibold">Markets & Industries</h2>
            <div className="grid gap-4 ">
              <label className="grid gap-1">
                <span className={labelClass}>Focus Markets</span>
                <CheckboxGroup field="focus_markets" options={FOCUS_MARKETS} />
              </label>
              <label className="grid gap-1">
                <span className={labelClass}>Focus Industries</span>
                <CheckboxGroup field="focus_industries" options={FOCUS_INDUSTRIES} />
              </label>
            </div>
          </section>

          <section id="capital" className="rounded-lg border bg-card p-5 shadow-sm scroll-mt-20">
            <h2 className="mb-4 text-base font-semibold">Capital & Strategy</h2>
            <div className="grid gap-4 sm:grid-cols-2 ">
              <label className="grid gap-1">
                <span className={labelClass}>Holding Period</span>
                <select className={fieldClass} value={data.holding_period || ""} onChange={(e) => setData({ ...data, holding_period: e.target.value })}>
                  <option value="">Select...</option>
                  {HOLDING_PERIODS.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              </label>
              <label className="grid gap-1">
                <span className={labelClass}>Capital Scale</span>
                <select className={fieldClass} value={data.capital_scale || ""} onChange={(e) => setData({ ...data, capital_scale: e.target.value })}>
                  <option value="">Select...</option>
                  {CAPITAL_SCALES.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              </label>
              <label className="grid gap-1">
                <span className={labelClass}>Stock Investment Total</span>
                <input type="number" className={fieldClass} value={data.stock_invest_total || ""} onChange={(e) => setData({ ...data, stock_invest_total: Number(e.target.value) })} />
              </label>
              <label className="grid gap-1">
                <span className={labelClass}>Avoid Targets</span>
                <input className={fieldClass} value={(data.avoid_targets || []).join(", ")} onChange={(e) => setData({ ...data, avoid_targets: e.target.value.split(",").map((s: string) => s.trim()).filter(Boolean) })} placeholder="ST股, 次新股" />
              </label>
            </div>
            <label className="mt-4 grid gap-1 ">
              <span className={labelClass}>Custom Notes</span>
              <textarea className={fieldClass} rows={3} value={data.custom_notes || ""} onChange={(e) => setData({ ...data, custom_notes: e.target.value })} />
            </label>
          </section>
        </div>

        <aside className="hidden lg:block self-start sticky top-36">
          <h3 className="mb-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">Sections</h3>
          <SectionNav sections={sections} activeId={activeId} />
          <ActionBar saving={saving} onSave={save} onReset={reset} />
        </aside>
      </div>
  );
}

// ===== Password Change Section =====
function PasswordSection({ oldPwd, setOldPwd, newPwd, setNewPwd, confirmPwd, setConfirmPwd }: {
  oldPwd: string; setOldPwd: (v: string) => void;
  newPwd: string; setNewPwd: (v: string) => void;
  confirmPwd: string; setConfirmPwd: (v: string) => void;
}) {
  return (
    <section id="password" className="rounded-lg border bg-card p-5 shadow-sm scroll-mt-20">
      <div className="mb-4 flex items-center gap-2">
        <Lock className="h-4 w-4 text-primary" />
        <h2 className="text-base font-semibold">Change Password</h2>
      </div>
      <div className="grid gap-4 max-w-md">
        <label className="grid gap-1">
          <span className={labelClass}>Current Password</span>
          <input type="password" value={oldPwd} onChange={(e) => setOldPwd(e.target.value)} className={fieldClass} />
        </label>
        <label className="grid gap-1">
          <span className={labelClass}>New Password</span>
          <input type="password" value={newPwd} onChange={(e) => setNewPwd(e.target.value)} className={fieldClass} placeholder="Min 8 characters" />
        </label>
        <label className="grid gap-1">
          <span className={labelClass}>Confirm New Password</span>
          <input
            type="password"
            value={confirmPwd}
            onChange={(e) => setConfirmPwd(e.target.value)}
            className={fieldClass}
          />
          {confirmPwd && newPwd !== confirmPwd && (
            <span className="text-xs text-danger">Passwords do not match</span>
          )}
        </label>
      </div>
    </section>
  );
}

// ===== System Settings Page =====
function SystemPage() {
  const [data, setData] = useState<Record<string, any>>({});
  const [snapshot, setSnapshot] = useState<Record<string, any>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const sections = tabMeta.system.sections;
  const activeId = useActiveSection(sections.map((s) => s.id));

  useEffect(() => {
    api.getSettings()
      .then((d) => { setData(d); setSnapshot(JSON.parse(JSON.stringify(d))); })
      .catch((err) => toast.error(err.message))
      .finally(() => setLoading(false));
  }, []);

  const save = async () => {
    setSaving(true);
    try {
      await api.updateSettings(data);
      setSnapshot(JSON.parse(JSON.stringify(data)));
      toast.success("Settings saved");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const reset = () => setData({ ...snapshot });

  useCtrlS(save);

  if (loading) return <div className="flex items-center gap-2 p-12 text-muted-foreground"><Loader2 className="h-5 w-5 animate-spin" /> Loading...</div>;

  const limits = data.proposal_limits || { trend: 10, industry: 10, stock: 10 };

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_180px]">
      <div className="space-y-6">
          <section id="scheduler" className="rounded-lg border bg-card p-5 shadow-sm scroll-mt-20">
            <h2 className="mb-4 text-base font-semibold">Scheduler</h2>
            <div className="grid gap-4 sm:grid-cols-2 ">
              <label className="grid gap-1">
                <span className={labelClass}>News Archive Time</span>
                <input type="time" className={fieldClass} value={data.news_archive_time || "08:00"} onChange={(e) => setData({ ...data, news_archive_time: e.target.value })} />
              </label>
              <label className="grid gap-1">
                <span className={labelClass}>Sentinel Interval (minutes)</span>
                <input type="number" className={fieldClass} min={10} max={1440} value={data.sentinel_interval || 60} onChange={(e) => setData({ ...data, sentinel_interval: Number(e.target.value) })} />
              </label>
            </div>
          </section>

          <section id="proposals" className="rounded-lg border bg-card p-5 shadow-sm scroll-mt-20">
            <h2 className="mb-4 text-base font-semibold">Proposal Limits</h2>
            <div className="grid gap-4 grid-cols-3 ">
              <label className="grid gap-1">
                <span className={hintClass}>Trend</span>
                <input type="number" className={fieldClass} min={1} value={limits.trend} onChange={(e) => setData({ ...data, proposal_limits: { ...limits, trend: Number(e.target.value) } })} />
              </label>
              <label className="grid gap-1">
                <span className={hintClass}>Industry</span>
                <input type="number" className={fieldClass} min={1} value={limits.industry} onChange={(e) => setData({ ...data, proposal_limits: { ...limits, industry: Number(e.target.value) } })} />
              </label>
              <label className="grid gap-1">
                <span className={hintClass}>Stock</span>
                <input type="number" className={fieldClass} min={1} value={limits.stock} onChange={(e) => setData({ ...data, proposal_limits: { ...limits, stock: Number(e.target.value) } })} />
              </label>
            </div>
          </section>
        </div>

        <aside className="hidden lg:block self-start sticky top-36">
          <h3 className="mb-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">Sections</h3>
          <SectionNav sections={sections} activeId={activeId} />
          <ActionBar saving={saving} onSave={save} onReset={reset} />
        </aside>
      </div>
  );
}

// ===== Security Page =====
function SecurityPage() {
  const sections = tabMeta.security.sections;
  const activeId = useActiveSection(sections.map((s) => s.id));
  const [oldPwd, setOldPwd] = useState("");
  const [newPwd, setNewPwd] = useState("");
  const [confirmPwd, setConfirmPwd] = useState("");
  const [saving, setSaving] = useState(false);

  const save = async () => {
    if (!oldPwd || !newPwd) { toast.error("Please fill in all fields"); return; }
    if (newPwd.length < 8) { toast.error("New password must be at least 8 characters"); return; }
    if (newPwd !== confirmPwd) { toast.error("Passwords do not match"); return; }
    setSaving(true);
    try {
      await api.changePassword(oldPwd, newPwd);
      toast.success("Password updated");
      setOldPwd(""); setNewPwd(""); setConfirmPwd("");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to change password");
    } finally {
      setSaving(false);
    }
  };

  const reset = () => { setOldPwd(""); setNewPwd(""); setConfirmPwd(""); };

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_180px]">
      <div className="space-y-6">
        <PasswordSection oldPwd={oldPwd} setOldPwd={setOldPwd} newPwd={newPwd} setNewPwd={setNewPwd} confirmPwd={confirmPwd} setConfirmPwd={setConfirmPwd} />
      </div>
      <aside className="hidden lg:block self-start sticky top-36">
        <h3 className="mb-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">Sections</h3>
        <SectionNav sections={sections} activeId={activeId} />
        <ActionBar saving={saving} onSave={save} onReset={reset} />
      </aside>
    </div>
  );
}

// ===== Main Settings Page =====
export function Settings() {
  const { t } = useI18n();
  const [tab, setTab] = useState<TabKey>("llm");

  return (
    <div>
      {/* Sticky header */}
      <div className="sticky top-0 z-10 bg-background border-b px-6 py-4">
        <div className="mb-3">
          <h1 className="text-2xl font-semibold tracking-tight">{t.settings}</h1>
          <p className="text-sm text-muted-foreground">{t.settingsDesc}</p>
        </div>
        <div className="flex gap-1 rounded-lg bg-muted p-1">
          {TABS.map((key) => {
            const meta = tabMeta[key];
            const Icon = meta.icon;
            return (
              <button
                key={key}
                onClick={() => setTab(key)}
                className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition ${
                  tab === key ? "bg-background shadow-sm" : "text-muted-foreground hover:text-foreground"
                }`}
              >
                <Icon className="h-4 w-4" />
                {meta.label}
              </button>
            );
          })}
        </div>
      </div>

      <div className="p-6 pt-4">
        {tab === "llm" && <LLMDataPage />}
        {tab === "preferences" && <PreferencesPage />}
        {tab === "system" && <SystemPage />}
        {tab === "security" && <SecurityPage />}
      </div>
    </div>
  );
}
