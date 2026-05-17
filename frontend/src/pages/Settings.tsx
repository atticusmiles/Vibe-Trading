import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { Loader2, Lock, RotateCcw, Save, Wrench, Briefcase } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

const fieldClass =
  "w-full rounded-md border bg-background px-3 py-2 text-sm outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/20 disabled:cursor-not-allowed disabled:opacity-60";
const labelClass = "text-sm font-medium";
const hintClass = "text-xs text-muted-foreground";

const TABS = ["preferences", "system", "security"] as const;
type TabKey = (typeof TABS)[number];

const tabMeta: Record<TabKey, { label: string; icon: typeof Wrench; sections: { id: string; label: string }[] }> = {
  preferences: {
    label: "投资偏好",
    icon: Briefcase,
    sections: [
      { id: "invest-style", label: "投资风格" },
      { id: "markets", label: "市场与行业" },
      { id: "capital", label: "资金与策略" },
    ],
  },
  system: {
    label: "系统设置",
    icon: Wrench,
    sections: [
      { id: "scheduler", label: "调度器" },
      { id: "proposals", label: "提案限制" },
    ],
  },
  security: {
    label: "安全",
    icon: Lock,
    sections: [
      { id: "password", label: "修改密码" },
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
        保存
      </button>
      <button
        type="button"
        onClick={onReset}
        className="inline-flex w-full items-center justify-center gap-1.5 rounded-md border px-3 py-1.5 text-sm text-muted-foreground transition hover:bg-muted hover:text-foreground"
      >
        <RotateCcw className="h-3.5 w-3.5" />
        重置
      </button>
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
      .catch((err) => toast.error(err instanceof Error ? err.message : "偏好加载失败"))
      .finally(() => setLoading(false));
  }, []);

  const save = async () => {
    setSaving(true);
    try {
      await api.updatePreferences(data);
      setSnapshot(JSON.parse(JSON.stringify(data)));
      toast.success("偏好已保存");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "保存失败");
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

  if (loading) return <div className="flex items-center gap-2 p-12 text-muted-foreground"><Loader2 className="h-5 w-5 animate-spin" /> 加载中...</div>;

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_180px]">
      <div className="space-y-6">
          <section id="invest-style" className="rounded-lg border bg-card p-5 shadow-sm scroll-mt-20">
            <h2 className="mb-4 text-base font-semibold">投资风格</h2>
            <div className="grid gap-4 sm:grid-cols-2 ">
              <label className="grid gap-1">
                <span className={labelClass}>风格</span>
                <select className={fieldClass} value={data.investment_style || ""} onChange={(e) => setData({ ...data, investment_style: e.target.value })}>
                  <option value="">请选择...</option>
                  {INVESTMENT_STYLES.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              </label>
              <label className="grid gap-1">
                <span className={labelClass}>风险偏好</span>
                <select className={fieldClass} value={data.risk_appetite || ""} onChange={(e) => setData({ ...data, risk_appetite: e.target.value })}>
                  <option value="">请选择...</option>
                  {RISK_APPETITES.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              </label>
            </div>
          </section>

          <section id="markets" className="rounded-lg border bg-card p-5 shadow-sm scroll-mt-20">
            <h2 className="mb-4 text-base font-semibold">市场与行业</h2>
            <div className="grid gap-4 ">
              <label className="grid gap-1">
                <span className={labelClass}>关注市场</span>
                <CheckboxGroup field="focus_markets" options={FOCUS_MARKETS} />
              </label>
              <label className="grid gap-1">
                <span className={labelClass}>关注行业</span>
                <CheckboxGroup field="focus_industries" options={FOCUS_INDUSTRIES} />
              </label>
            </div>
          </section>

          <section id="capital" className="rounded-lg border bg-card p-5 shadow-sm scroll-mt-20">
            <h2 className="mb-4 text-base font-semibold">资金与策略</h2>
            <div className="grid gap-4 sm:grid-cols-2 ">
              <label className="grid gap-1">
                <span className={labelClass}>持仓周期</span>
                <select className={fieldClass} value={data.holding_period || ""} onChange={(e) => setData({ ...data, holding_period: e.target.value })}>
                  <option value="">请选择...</option>
                  {HOLDING_PERIODS.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              </label>
              <label className="grid gap-1">
                <span className={labelClass}>资金规模</span>
                <select className={fieldClass} value={data.capital_scale || ""} onChange={(e) => setData({ ...data, capital_scale: e.target.value })}>
                  <option value="">请选择...</option>
                  {CAPITAL_SCALES.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              </label>
              <label className="grid gap-1">
                <span className={labelClass}>股票投资总额</span>
                <input type="number" className={fieldClass} value={data.stock_invest_total || ""} onChange={(e) => setData({ ...data, stock_invest_total: Number(e.target.value) })} />
              </label>
              <label className="grid gap-1">
                <span className={labelClass}>回避标的</span>
                <input className={fieldClass} value={(data.avoid_targets || []).join(", ")} onChange={(e) => setData({ ...data, avoid_targets: e.target.value.split(",").map((s: string) => s.trim()).filter(Boolean) })} placeholder="ST股, 次新股" />
              </label>
            </div>
            <label className="mt-4 grid gap-1 ">
              <span className={labelClass}>自定义备注</span>
              <textarea className={fieldClass} rows={3} value={data.custom_notes || ""} onChange={(e) => setData({ ...data, custom_notes: e.target.value })} />
            </label>
          </section>
        </div>

        <aside className="hidden lg:block self-start sticky top-36">
          <h3 className="mb-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">章节</h3>
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
        <h2 className="text-base font-semibold">修改密码</h2>
      </div>
      <div className="grid gap-4 max-w-md">
        <label className="grid gap-1">
          <span className={labelClass}>当前密码</span>
          <input type="password" value={oldPwd} onChange={(e) => setOldPwd(e.target.value)} className={fieldClass} />
        </label>
        <label className="grid gap-1">
          <span className={labelClass}>新密码</span>
          <input type="password" value={newPwd} onChange={(e) => setNewPwd(e.target.value)} className={fieldClass} placeholder="最少 8 个字符" />
        </label>
        <label className="grid gap-1">
          <span className={labelClass}>确认新密码</span>
          <input
            type="password"
            value={confirmPwd}
            onChange={(e) => setConfirmPwd(e.target.value)}
            className={fieldClass}
          />
          {confirmPwd && newPwd !== confirmPwd && (
            <span className="text-xs text-danger">两次密码不一致</span>
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
      .catch((err) => toast.error(err instanceof Error ? err.message : "设置加载失败"))
      .finally(() => setLoading(false));
  }, []);

  const save = async () => {
    setSaving(true);
    try {
      await api.updateSettings(data);
      setSnapshot(JSON.parse(JSON.stringify(data)));
      toast.success("设置已保存");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "保存失败");
    } finally {
      setSaving(false);
    }
  };

  const reset = () => setData({ ...snapshot });

  useCtrlS(save);

  if (loading) return <div className="flex items-center gap-2 p-12 text-muted-foreground"><Loader2 className="h-5 w-5 animate-spin" /> 加载中...</div>;

  const limits = data.proposal_limits || { trend: 10, industry: 10, stock: 10 };

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_180px]">
      <div className="space-y-6">
          <section id="scheduler" className="rounded-lg border bg-card p-5 shadow-sm scroll-mt-20">
            <h2 className="mb-4 text-base font-semibold">调度器</h2>
            <div className="grid gap-4 sm:grid-cols-2 ">
              <label className="grid gap-1">
                <span className={labelClass}>新闻归档时间</span>
                <input type="time" className={fieldClass} value={data.news_archive_time || "08:00"} onChange={(e) => setData({ ...data, news_archive_time: e.target.value })} />
              </label>
              <label className="grid gap-1">
                <span className={labelClass}>哨兵间隔（分钟）</span>
                <input type="number" className={fieldClass} min={10} max={1440} value={data.sentinel_interval || 60} onChange={(e) => setData({ ...data, sentinel_interval: Number(e.target.value) })} />
              </label>
            </div>
          </section>

          <section id="proposals" className="rounded-lg border bg-card p-5 shadow-sm scroll-mt-20">
            <h2 className="mb-4 text-base font-semibold">提案限制</h2>
            <div className="grid gap-4 grid-cols-3 ">
              <label className="grid gap-1">
                <span className={hintClass}>趋势</span>
                <input type="number" className={fieldClass} min={1} value={limits.trend} onChange={(e) => setData({ ...data, proposal_limits: { ...limits, trend: Number(e.target.value) } })} />
              </label>
              <label className="grid gap-1">
                <span className={hintClass}>行业</span>
                <input type="number" className={fieldClass} min={1} value={limits.industry} onChange={(e) => setData({ ...data, proposal_limits: { ...limits, industry: Number(e.target.value) } })} />
              </label>
              <label className="grid gap-1">
                <span className={hintClass}>自选股</span>
                <input type="number" className={fieldClass} min={1} value={limits.stock} onChange={(e) => setData({ ...data, proposal_limits: { ...limits, stock: Number(e.target.value) } })} />
              </label>
            </div>
          </section>
        </div>

        <aside className="hidden lg:block self-start sticky top-36">
          <h3 className="mb-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">章节</h3>
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
    if (!oldPwd || !newPwd) { toast.error("请填写所有字段"); return; }
    if (newPwd.length < 8) { toast.error("新密码至少 8 个字符"); return; }
    if (newPwd !== confirmPwd) { toast.error("两次密码不一致"); return; }
    setSaving(true);
    try {
      await api.changePassword(oldPwd, newPwd);
      toast.success("密码已更新");
      setOldPwd(""); setNewPwd(""); setConfirmPwd("");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "密码修改失败");
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
        <h3 className="mb-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">章节</h3>
        <SectionNav sections={sections} activeId={activeId} />
        <ActionBar saving={saving} onSave={save} onReset={reset} />
      </aside>
    </div>
  );
}

// ===== Main Settings Page =====
export function Settings() {
  const { t } = useI18n();
  const [tab, setTab] = useState<TabKey>("preferences");

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
        {tab === "preferences" && <PreferencesPage />}
        {tab === "system" && <SystemPage />}
        {tab === "security" && <SecurityPage />}
      </div>
    </div>
  );
}
