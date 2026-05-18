import { Link } from "react-router-dom";
import { TrendingUp, Factory, CandlestickChart, Clock, ArrowRight } from "lucide-react";
import { api, type DashboardData, type RecentlyUpdatedItem } from "@/lib/api";
import { StatusDot } from "@/components/fact-tables/StatusDot";
import { ConfidenceDot } from "@/components/fact-tables/ConfidenceDot";
import { useEffect, useState } from "react";
import { Skeleton } from "@/components/common/Skeleton";

const TYPE_ICONS: Record<string, typeof TrendingUp> = { trend: TrendingUp, industry: Factory, stock: CandlestickChart };

function StatCard({ title, active, proposed, to }: { title: string; active: number; proposed: number; to: string }) {
  return (
    <Link to={to} className="rounded-lg border bg-card p-4 transition hover:border-primary/50 hover:shadow-sm">
      <p className="text-xs font-medium text-muted-foreground">{title}</p>
      <p className="mt-1 text-2xl font-bold">{active}</p>
      {proposed > 0 && <p className="text-xs text-warning">+{proposed} 提议中</p>}
    </Link>
  );
}

function relativeTime(iso: string | null): string {
  if (!iso) return "";
  const diff = Date.now() - new Date(iso + "Z").getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "刚刚";
  if (mins < 60) return `${mins}分钟前`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}小时前`;
  return `${Math.floor(hrs / 24)}天前`;
}

export function Home() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    api.getDashboard().then(setData).catch(() => setError(true));
  }, []);

  if (error) return <div className="p-8 text-center text-muted-foreground">仪表盘加载失败</div>;
  if (!data) return <div className="p-8"><Skeleton /></div>;

  const s = data.stats;
  const active = (m: Record<string, number>) => (m.proposed || 0) + (m.adopted || 0);

  return (
    <div className="space-y-6 p-6">
      <h1 className="text-lg font-semibold">仪表盘</h1>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard title="活跃趋势" active={active(s.trends)} proposed={s.trends.proposed || 0} to="/trends?status=active" />
        <StatCard title="活跃行业" active={active(s.industries)} proposed={s.industries.proposed || 0} to="/industries?status=active" />
        <StatCard title="活跃自选股" active={active(s.stocks)} proposed={s.stocks.proposed || 0} to="/stocks?status=active" />
        <Link to="/proposals" className="rounded-lg border bg-card p-4 transition hover:border-primary/50 hover:shadow-sm">
          <p className="text-xs font-medium text-muted-foreground">待审批提案</p>
          <p className="mt-1 text-2xl font-bold">
            {Object.values(data.pending_proposals || {}).reduce((a, b) => a + b, 0) || 0}
          </p>
          {(data.pending_proposals?.trend || 0) > 0 && <p className="text-xs text-warning">趋势 {data.pending_proposals!.trend}</p>}
        </Link>
      </div>

      <div className="grid gap-4 lg:grid-cols-[3fr_2fr]">
        <div className="rounded-lg border bg-card p-5">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold">最近更新</h2>
            <Link to="/trends" className="text-xs text-primary hover:underline">全部</Link>
          </div>
          {data.recently_updated.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">暂无近期活动</p>
          ) : (
            <div className="space-y-1">
              {data.recently_updated.map((item: RecentlyUpdatedItem) => {
                const Icon = TYPE_ICONS[item.type] || TrendingUp;
                return (
                  <Link key={`${item.type}-${item.id}`} to={`/${item.type === "trend" ? "trends" : item.type === "industry" ? "industries" : "stocks"}#${item.id}`}
                    className="flex items-center gap-3 rounded-md px-2 py-2 text-sm transition hover:bg-muted/50">
                    <Icon className="h-4 w-4 shrink-0 text-muted-foreground" />
                    <span className="flex-1 truncate">{item.title}</span>
                    <ConfidenceDot value={item.confidence} />
                    <span className="shrink-0 text-xs text-muted-foreground">{relativeTime(item.updated_at)}</span>
                  </Link>
                );
              })}
            </div>
          )}
        </div>

        <div className="rounded-lg border bg-card p-5">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold">最近运行</h2>
            <Link to="/agent" className="text-xs text-primary hover:underline">全部</Link>
          </div>
          {data.latest_runs.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">暂无运行记录</p>
          ) : (
            <div className="space-y-1">
              {data.latest_runs.map((r) => (
                <Link key={r.run_id} to={`/runs/${r.run_id}`}
                  className="flex items-center gap-2 rounded-md px-2 py-2 text-sm transition hover:bg-muted/50">
                  <CandlestickChart className="h-4 w-4 shrink-0 text-muted-foreground" />
                  <span className="truncate font-mono text-xs">{r.run_id}</span>
                  <ArrowRight className="ml-auto h-3 w-3 text-muted-foreground" />
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
