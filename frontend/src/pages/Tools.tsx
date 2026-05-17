import { useState } from "react";
import { BarChart3, Loader2 } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { api } from "@/lib/api";
import { CorrelationMatrix } from "@/components/charts/CorrelationMatrix";

const fieldClass =
  "w-full rounded-md border bg-background px-3 py-2 text-sm outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/20 disabled:cursor-not-allowed disabled:opacity-60";
const labelClass = "text-sm font-medium";

const TABS = ["correlation"] as const;
type TabKey = (typeof TABS)[number];

const tabMeta: Record<TabKey, { label: string; icon: typeof BarChart3 }> = {
  correlation: { label: "相关性矩阵", icon: BarChart3 },
};

const WINDOWS = [30, 60, 90, 180, 365] as const;

function CorrelationPage() {
  const { t } = useI18n();
  const [codes, setCodes] = useState("BTC-USDT,ETH-USDT,SPY,AAPL");
  const [days, setDays] = useState<number>(90);
  const [method, setMethod] = useState<"pearson" | "spearman">("pearson");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [labels, setLabels] = useState<string[]>([]);
  const [matrix, setMatrix] = useState<number[][]>([]);

  const compute = async () => {
    setError(null);
    setLoading(true);
    try {
      const result = await api.computeCorrelation(codes, days, method);
      setLabels(result.labels);
      setMatrix(result.matrix);
    } catch (e) {
      setError(e instanceof Error ? e.message : "相关性计算失败");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 rounded-lg border bg-card p-5 shadow-sm">
        <label className="grid gap-1.5">
          <span className={labelClass}>资产代码</span>
          <input
            type="text"
            value={codes}
            onChange={(e) => setCodes(e.target.value)}
            placeholder="BTC-USDT,ETH-USDT,SPY"
            className={fieldClass}
          />
          <span className="text-xs text-muted-foreground">逗号分隔，例如 BTC-USDT,ETH-USDT,AAPL,SPY</span>
        </label>

        <div className="flex flex-wrap gap-6">
          <label className="grid gap-1.5">
            <span className={labelClass}>窗口</span>
            <div className="flex gap-1.5">
              {WINDOWS.map((w) => (
                <button
                  key={w}
                  onClick={() => setDays(w)}
                  className={`px-3 py-1 rounded text-sm border transition-colors ${
                    days === w ? "bg-primary text-primary-foreground" : "border-muted-foreground/30 hover:border-primary"
                  }`}
                >
                  {w}d
                </button>
              ))}
            </div>
          </label>

          <label className="grid gap-1.5">
            <span className={labelClass}>方法</span>
            <div className="flex gap-1.5">
              {(["pearson", "spearman"] as const).map((m) => (
                <button
                  key={m}
                  onClick={() => setMethod(m)}
                  className={`px-3 py-1 rounded text-sm border transition-colors capitalize ${
                    method === m ? "bg-primary text-primary-foreground" : "border-muted-foreground/30 hover:border-primary"
                  }`}
                >
                  {m}
                </button>
              ))}
            </div>
          </label>
        </div>

        <button
          onClick={compute}
          disabled={loading}
          className="self-start inline-flex items-center gap-1.5 rounded-md bg-primary px-4 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
        >
          {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <BarChart3 className="h-3.5 w-3.5" />}
          计算
        </button>
      </div>

      {error && (
        <div className="text-sm text-danger border border-danger/30 rounded-md p-3 bg-danger/5">
          {error}
        </div>
      )}

      {labels.length > 0 && <CorrelationMatrix labels={labels} matrix={matrix} height={520} />}
    </div>
  );
}

export function Tools() {
  const { t } = useI18n();
  const [tab, setTab] = useState<TabKey>("correlation");

  return (
    <div>
      <div className="sticky top-0 z-10 bg-background border-b px-6 py-4">
        <div className="mb-3">
          <h1 className="text-2xl font-semibold tracking-tight">工具</h1>
          <p className="text-sm text-muted-foreground">分析和实用工具</p>
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
        {tab === "correlation" && <CorrelationPage />}
      </div>
    </div>
  );
}
