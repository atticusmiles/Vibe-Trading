import { useEffect, useState, useCallback } from "react";
import { Newspaper, RefreshCw, ChevronDown, ChevronUp, FileText, Zap } from "lucide-react";
import { toast } from "sonner";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api, type NewsDigestItem, type NewsItem } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

export function News() {
  const { t } = useI18n();
  const [digests, setDigests] = useState<NewsDigestItem[]>([]);
  const [recentNews, setRecentNews] = useState<NewsItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [expandedDigest, setExpandedDigest] = useState<number | null>(null);

  const loadData = useCallback(async () => {
    try {
      const [d, n] = await Promise.all([api.listNewsDigests(), api.listRecentNews({ limit: 30 })]);
      setDigests(d);
      setRecentNews(n);
    } catch {
      toast.error("加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const handleTrigger = async () => {
    setGenerating(true);
    try {
      await api.triggerDigest();
      toast.success(t.digestGenerated);
      await loadData();
    } catch {
      toast.error(t.digestTriggerFailed);
    } finally {
      setGenerating(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[60vh] text-muted-foreground">
        {t.loading}
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Newspaper className="h-5 w-5 text-primary" />
          <h1 className="text-lg font-semibold">{t.news}</h1>
        </div>
        <button
          onClick={handleTrigger}
          disabled={generating}
          className={cn(
            "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors",
            generating
              ? "bg-muted text-muted-foreground cursor-not-allowed"
              : "bg-primary text-primary-foreground hover:bg-primary/90",
          )}
        >
          <RefreshCw className={cn("h-3.5 w-3.5", generating && "animate-spin")} />
          {generating ? t.digestGenerating : t.triggerDigest}
        </button>
      </div>

      {/* Digests section */}
      <section>
        <h2 className="flex items-center gap-2 text-sm font-medium text-muted-foreground mb-3">
          <FileText className="h-4 w-4" />
          {t.newsDigests}
        </h2>
        {digests.length === 0 ? (
          <p className="text-sm text-muted-foreground/60 py-4">{t.noDigests}</p>
        ) : (
          <div className="space-y-3">
            {digests.map((d) => {
              const isExpanded = expandedDigest === d.id;
              return (
                <div key={d.id} className="border rounded-lg bg-card">
                  <button
                    onClick={() => setExpandedDigest(isExpanded ? null : d.id)}
                    className="w-full flex items-start justify-between px-4 py-3 text-left hover:bg-muted/30 transition-colors"
                  >
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium">{d.digest_date}</div>
                      {d.summary && (
                        <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{d.summary}</p>
                      )}
                    </div>
                    {isExpanded ? (
                      <ChevronUp className="h-4 w-4 text-muted-foreground shrink-0 ml-2" />
                    ) : (
                      <ChevronDown className="h-4 w-4 text-muted-foreground shrink-0 ml-2" />
                    )}
                  </button>
                  {isExpanded && (
                    <div className="px-4 pb-4 border-t">
                      <div className="prose prose-sm dark:prose-invert max-w-none text-sm mt-3">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                          {d.content}
                        </ReactMarkdown>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </section>

      {/* Recent news section */}
      <section>
        <h2 className="flex items-center gap-2 text-sm font-medium text-muted-foreground mb-3">
          <Zap className="h-4 w-4" />
          {t.recentNews}
        </h2>
        {recentNews.length === 0 ? (
          <p className="text-sm text-muted-foreground/60 py-4">{t.noData}</p>
        ) : (
          <div className="space-y-2">
            {recentNews.map((n) => (
              <div key={n.id} className="border rounded-lg px-4 py-3 bg-card hover:bg-muted/20 transition-colors">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium leading-snug">{n.title}</p>
                    {n.content && (
                      <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{n.content}</p>
                    )}
                  </div>
                  <div className="flex flex-col items-end gap-1 shrink-0">
                    <span className="text-[10px] text-muted-foreground/60">{n.source}</span>
                    <span className="text-[10px] text-muted-foreground/60">
                      {new Date(n.published_at).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" })}
                    </span>
                    {n.level && (
                      <span className={cn(
                        "text-[10px] px-1.5 py-0.5 rounded font-medium",
                        n.level === "重要" ? "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400" :
                        n.level === "利好" ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400" :
                        "bg-muted text-muted-foreground",
                      )}>
                        {n.level}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
