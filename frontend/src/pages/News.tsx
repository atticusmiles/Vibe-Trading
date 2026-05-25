import { useEffect, useState, useCallback, useRef } from "react";
import {
  Newspaper, RefreshCw, ChevronDown, ChevronUp,
  FileText, Zap, ChevronLeft, ChevronRight,
} from "lucide-react";
import { toast } from "sonner";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api, type NewsDigestItem, type NewsItem } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

type Tab = "home" | "feed" | "digests";

const MarkdownBlock = ({ content }: { content: string }) => (
  <div className="prose prose-sm dark:prose-invert max-w-none text-sm">
    <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
  </div>
);

/* ───── Auto-scrolling news feed box ───── */
function AutoScrollFeed({ items }: { items: NewsItem[] }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [paused, setPaused] = useState(false);
  const userScrolledAway = useRef(false);

  // Detect user scroll — pause auto when they scroll up
  const handleScroll = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 60;
    userScrolledAway.current = !atBottom;
  }, []);

  // Auto-scroll when user hasn't scrolled away
  useEffect(() => {
    const el = containerRef.current;
    if (!el || items.length === 0 || paused) return;

    const speed = 25; // px/s
    let rafId: number;
    let last = performance.now();

    const step = (now: number) => {
      if (!el) return;
      const dt = (now - last) / 1000;
      last = now;
      if (!userScrolledAway.current) {
        el.scrollTop += speed * dt;
      }
      rafId = requestAnimationFrame(step);
    };

    rafId = requestAnimationFrame(step);
    return () => cancelAnimationFrame(rafId);
  }, [items, paused]);

  // When new items arrive, smooth-scroll to bottom if user hasn't scrolled away
  useEffect(() => {
    if (!userScrolledAway.current && containerRef.current) {
      containerRef.current.scrollTo({
        top: containerRef.current.scrollHeight,
        behavior: 'smooth',
      });
    }
  }, [items]);

  if (items.length === 0) {
    return <p className="text-xs text-muted-foreground/60 py-4">暂无新闻</p>;
  }

  return (
    <div
      ref={containerRef}
      onScroll={handleScroll}
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      className="h-[400px] overflow-y-auto rounded-lg border"
    >
      <div className="space-y-1.5 p-3">
        {items.map((n) => (
          <NewsItemRow key={n.id} item={n} />
        ))}
      </div>
    </div>
  );
}

/* ───── Tab 1: 概览 ───── */
function NewsHome() {
  const { t } = useI18n();
  const [digests, setDigests] = useState<NewsDigestItem[]>([]);
  const [news, setNews] = useState<NewsItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedDigest, setExpandedDigest] = useState<number | null>(null);
  const [regeneratingIds, setRegeneratingIds] = useState<Set<number>>(new Set());

  const loadAll = useCallback(async (showLoading = false) => {
    if (showLoading) setLoading(true);
    try {
      const [d, n] = await Promise.all([
        api.listNewsDigests(),
        api.listRecentNews({ limit: 30 }),
      ]);
      setDigests(d.slice(0, 3));
      setNews(n);
    } catch {
      // silent on poll
    } finally {
      if (showLoading) setLoading(false);
    }
  }, []);

  // Initial load
  useEffect(() => { loadAll(true); }, [loadAll]);

  // Real-time polling every 15s
  useEffect(() => {
    const id = setInterval(() => loadAll(false), 15000);
    return () => clearInterval(id);
  }, [loadAll]);

  const handleRegenerate = async (id: number, date: string) => {
    setRegeneratingIds((prev) => new Set(prev).add(id));
    try {
      await api.triggerDigest(date);
      toast.success(`${date} 摘要已重新生成`);
      await loadAll(false);
    } catch {
      toast.error(`${date} 重新生成失败`);
    } finally {
      setRegeneratingIds((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    }
  };

  if (loading) {
    return <div className="flex items-center justify-center h-[40vh] text-muted-foreground text-sm">{t.loading}</div>;
  }

  return (
    <div className="space-y-6">
      {/* Recent digests */}
      <section>
        <h2 className="flex items-center gap-2 text-sm font-semibold text-foreground mb-3">
          <FileText className="h-4 w-4 text-primary" />
          最近摘要
        </h2>
        {digests.length === 0 ? (
          <p className="text-xs text-muted-foreground/60 py-4">{t.noDigests}</p>
        ) : (
          <div className="space-y-2">
            {digests.map((d) => {
              const expanded = expandedDigest === d.id;
              const isRegenerating = regeneratingIds.has(d.id);
              return (
                <div key={d.id} className="rounded-lg border bg-card">
                  <button
                    onClick={() => setExpandedDigest(expanded ? null : d.id)}
                    className="flex w-full items-center justify-between gap-3 px-4 py-2.5 text-left hover:bg-muted/30 transition-colors"
                  >
                    <div className="min-w-0 flex-1">
                      <span className="text-sm font-medium">{d.digest_date}</span>
                      {d.summary && (
                        <p className="mt-0.5 text-xs text-muted-foreground line-clamp-1">{d.summary}</p>
                      )}
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <button
                        onClick={(e) => { e.stopPropagation(); handleRegenerate(d.id, d.digest_date); }}
                        disabled={isRegenerating}
                        className={cn(
                          "inline-flex items-center gap-1 rounded px-2 py-1 text-[10px] font-medium transition-colors",
                          isRegenerating
                            ? "text-muted-foreground/40 cursor-not-allowed"
                            : "text-muted-foreground hover:text-foreground hover:bg-muted/50",
                        )}
                      >
                        <RefreshCw className={cn("h-3 w-3", isRegenerating && "animate-spin")} />
                        {isRegenerating ? "生成中..." : "重新生成"}
                      </button>
                      {expanded ? (
                        <ChevronUp className="h-4 w-4 text-muted-foreground" />
                      ) : (
                        <ChevronDown className="h-4 w-4 text-muted-foreground" />
                      )}
                    </div>
                  </button>
                  {expanded && (
                    <div className="border-t px-4 pb-4 pt-3">
                      <MarkdownBlock content={d.content} />
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </section>

      {/* Latest news feed */}
      <section>
        <h2 className="flex items-center gap-2 text-sm font-semibold text-foreground mb-3">
          <Zap className="h-4 w-4 text-primary" />
          实时新闻流
        </h2>
        <AutoScrollFeed items={news} />
      </section>
    </div>
  );
}

/* ───── Shared news list item ───── */
function NewsItemRow({ item }: { item: NewsItem }) {
  return (
    <div className="rounded-lg border bg-card px-4 py-2.5 hover:bg-muted/20 transition-colors">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium leading-snug">{item.title}</p>
          {item.content && (
            <p className="mt-0.5 text-xs text-muted-foreground line-clamp-2">{item.content}</p>
          )}
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1">
          <span className="text-[10px] text-muted-foreground/60">{item.source}</span>
          <span className="text-[10px] text-muted-foreground/60">
            {new Date(item.published_at).toLocaleString("zh-CN", {
              month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
            })}
          </span>
          {item.level && (
            <span className={cn(
              "text-[10px] px-1.5 py-0.5 rounded font-medium",
              item.level === "重要" ? "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400" :
              item.level === "利好" ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400" :
              "bg-muted text-muted-foreground",
            )}>
              {item.level}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

function NewsFeedList({ items, loading }: { items: NewsItem[]; loading?: boolean }) {
  if (loading) {
    return <div className="flex items-center justify-center py-8 text-xs text-muted-foreground">加载中...</div>;
  }
  if (items.length === 0) {
    return <p className="text-xs text-muted-foreground/60 py-4">暂无新闻</p>;
  }
  return (
    <div className="space-y-1.5">
      {items.map((n) => (
        <NewsItemRow key={n.id} item={n} />
      ))}
    </div>
  );
}

/* ───── Date helpers ───── */
function fmtDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function addDays(date: Date, n: number): Date {
  const d = new Date(date);
  d.setDate(d.getDate() + n);
  return d;
}

/* ───── Tab 2: 新闻流 ───── */
function NewsFeed() {
  const [items, setItems] = useState<NewsItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [currentDate, setCurrentDate] = useState(() => fmtDate(new Date()));
  const [loadedDates, setLoadedDates] = useState<string[]>([]);
  const today = fmtDate(new Date());
  const scrollRef = useRef<HTMLDivElement>(null);

  const fetchDate = useCallback(async (date: string): Promise<NewsItem[]> => {
    try {
      return await api.listRecentNews({ start_date: date, end_date: date + " 23:59:59", limit: 200 });
    } catch {
      return [];
    }
  }, []);

  // Load today on mount
  useEffect(() => {
    (async () => {
      setLoading(true);
      const data = await fetchDate(currentDate);
      setItems(data);
      setLoadedDates([currentDate]);
      setLoading(false);
    })();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const goToDate = async (date: string) => {
    setCurrentDate(date);
    setLoading(true);
    const data = await fetchDate(date);
    setItems(data);
    setLoadedDates([date]);
    setLoading(false);
  };

  const handleSync = async () => {
    setSyncing(true);
    try {
      const result = await api.syncNewsByDate(currentDate);
      toast.success(`同步完成，获取 ${result.synced} 条新闻`);
      // Refresh the list
      const data = await fetchDate(currentDate);
      setItems(data);
      setLoadedDates([currentDate]);
    } catch (e) {
      toast.error("同步失败");
    } finally {
      setSyncing(false);
    }
  };

  const loadMoreOlder = async () => {
    if (loadingMore) return;
    setLoadingMore(true);
    const oldest = [...loadedDates].sort()[0];
    const prev = fmtDate(addDays(new Date(oldest), -1));
    const data = await fetchDate(prev);
    if (data.length > 0) {
      setItems((prev) => [...prev, ...data]);
    }
    setLoadedDates((d) => [...d, prev]);
    setLoadingMore(false);
  };

  const canGoForward = currentDate !== today;

  return (
    <div className="flex flex-col h-full">
      {/* Date navigation */}
      <div className="flex items-center justify-between mb-4">
        <button
          onClick={() => goToDate(fmtDate(addDays(new Date(currentDate), -1)))}
          className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          <ChevronLeft className="h-3.5 w-3.5" /> 前一天
        </button>

        <div className="flex items-center gap-2">
          <input
            type="date"
            value={currentDate}
            max={today}
            onChange={(e) => goToDate(e.target.value)}
            onClick={(e) => e.currentTarget.showPicker?.()}
            className="w-36 rounded-md border bg-background px-2 py-1.5 text-xs font-semibold cursor-pointer"
          />
          <button
            onClick={handleSync}
            disabled={syncing}
            className="inline-flex items-center gap-1 rounded-md border px-2.5 py-1 text-xs text-muted-foreground hover:bg-muted transition-colors disabled:opacity-50"
          >
            <RefreshCw className={cn("h-3 w-3", syncing && "animate-spin")} />
            {syncing ? "同步中..." : "同步新闻"}
          </button>
        </div>

        <button
          onClick={() => canGoForward && goToDate(fmtDate(addDays(new Date(currentDate), 1)))}
          disabled={!canGoForward}
          className={cn(
            "inline-flex items-center gap-1 text-xs transition-colors",
            canGoForward ? "text-muted-foreground hover:text-foreground" : "text-muted-foreground/30 cursor-not-allowed",
          )}
        >
          后一天 <ChevronRight className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* News list */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto">
        <NewsFeedList items={items} loading={loading} />

        {!loading && items.length > 0 && (
          <div className="mt-3 flex justify-center">
            <button
              onClick={loadMoreOlder}
              disabled={loadingMore}
              className="inline-flex items-center gap-1 rounded-md border px-4 py-1.5 text-xs text-muted-foreground hover:bg-muted transition-colors disabled:opacity-50"
            >
              {loadingMore ? "加载中..." : "加载更早新闻"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

/* ───── Tab 3: 摘要页面 ───── */
function yesterdayStr(): string {
  const d = new Date();
  d.setDate(d.getDate() - 1);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function NewsDigests() {
  const { t } = useI18n();
  const [digests, setDigests] = useState<NewsDigestItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [visibleCount, setVisibleCount] = useState(10);
  const [generatingAll, setGeneratingAll] = useState(false);
  const [regeneratingIds, setRegeneratingIds] = useState<Set<number>>(new Set());
  const [targetDate, setTargetDate] = useState(yesterdayStr);
  const [startDate, setStartDate] = useState(() => {
    const d = new Date();
    d.setDate(d.getDate() - 30);
    return fmtDate(d);
  });
  const [endDate, setEndDate] = useState(() => fmtDate(new Date()));

  const loadDigests = useCallback(async (sd: string, ed: string) => {
    setLoading(true);
    try {
      const data = await api.listNewsDigests({ start_date: sd, end_date: ed + " 23:59:59" });
      setDigests(data);
    } catch {
      toast.error("加载摘要失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadDigests(startDate, endDate); }, [startDate, endDate, loadDigests]);

  const handleTriggerAll = async () => {
    setGeneratingAll(true);
    try {
      await api.triggerDigest(targetDate);
      toast.success(`${targetDate} 摘要已生成`);
      await loadDigests(startDate, endDate);
    } catch {
      toast.error(`${targetDate} 生成失败`);
    } finally {
      setGeneratingAll(false);
    }
  };

  const handleRegenerate = async (id: number, date: string) => {
    setRegeneratingIds((prev) => new Set(prev).add(id));
    try {
      await api.triggerDigest(date);
      toast.success(`${date} 摘要已重新生成`);
      await loadDigests(startDate, endDate);
    } catch {
      toast.error(`${date} 重新生成失败`);
    } finally {
      setRegeneratingIds((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    }
  };

  if (loading) {
    return <div className="flex items-center justify-center h-[40vh] text-muted-foreground text-sm">{t.loading}</div>;
  }

  const visible = digests.slice(0, visibleCount);
  const hasMore = visibleCount < digests.length;

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <h2 className="text-sm font-semibold flex items-center gap-2 shrink-0">
          <FileText className="h-4 w-4 text-primary" />
          每日市场摘要
        </h2>
        <div className="flex items-center gap-2">
          {/* Date range filter */}
          <div className="flex items-center gap-1 text-xs text-muted-foreground">
            <input
              type="date"
              value={startDate}
              max={endDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="w-32 rounded-md border bg-background px-2 py-1.5 text-xs outline-none"
            />
            <span>—</span>
            <input
              type="date"
              value={endDate}
              min={startDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="w-32 rounded-md border bg-background px-2 py-1.5 text-xs outline-none"
            />
          </div>
          <div className="w-px h-5 bg-border" />
          <input
            type="date"
            value={targetDate}
            onChange={(e) => setTargetDate(e.target.value)}
            max={yesterdayStr()}
            className="w-32 rounded-md border bg-background px-2 py-1.5 text-xs text-muted-foreground outline-none"
          />
          <button
            onClick={handleTriggerAll}
            disabled={generatingAll}
            className={cn(
              "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors shrink-0",
              generatingAll
                ? "bg-muted text-muted-foreground cursor-not-allowed"
                : "bg-primary text-primary-foreground hover:bg-primary/90",
            )}
          >
            <RefreshCw className={cn("h-3.5 w-3.5", generatingAll && "animate-spin")} />
            {generatingAll ? t.digestGenerating : t.triggerDigest}
          </button>
        </div>
      </div>

      {digests.length === 0 ? (
        <p className="text-xs text-muted-foreground/60 py-4">{t.noDigests}</p>
      ) : (
        <div className="space-y-2">
          {visible.map((d) => {
            const expanded = expandedId === d.id;
            const isRegenerating = regeneratingIds.has(d.id);
            return (
              <div key={d.id} className="rounded-lg border bg-card">
                <button
                  onClick={() => setExpandedId(expanded ? null : d.id)}
                  className="flex w-full items-center justify-between gap-3 px-4 py-2.5 text-left hover:bg-muted/30 transition-colors"
                >
                  <div className="min-w-0 flex-1">
                    <span className="text-sm font-medium">{d.digest_date}</span>
                    {d.summary && (
                      <p className="mt-0.5 text-xs text-muted-foreground line-clamp-1">{d.summary}</p>
                    )}
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <button
                      onClick={(e) => { e.stopPropagation(); handleRegenerate(d.id, d.digest_date); }}
                      disabled={isRegenerating}
                      className={cn(
                        "inline-flex items-center gap-1 rounded px-2 py-1 text-[10px] font-medium transition-colors",
                        isRegenerating
                          ? "text-muted-foreground/40 cursor-not-allowed"
                          : "text-muted-foreground hover:text-foreground hover:bg-muted/50",
                      )}
                    >
                      <RefreshCw className={cn("h-3 w-3", isRegenerating && "animate-spin")} />
                      {isRegenerating ? "生成中..." : "重新生成"}
                    </button>
                    {expanded ? (
                      <ChevronUp className="h-4 w-4 text-muted-foreground" />
                    ) : (
                      <ChevronDown className="h-4 w-4 text-muted-foreground" />
                    )}
                  </div>
                </button>
                {expanded && (
                  <div className="border-t px-4 pb-4 pt-3">
                    <MarkdownBlock content={d.content} />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Load more */}
      {hasMore && (
        <div className="flex justify-center pt-2">
          <button
            onClick={() => setVisibleCount((c) => c + 10)}
            className="inline-flex items-center gap-1 rounded-md border px-4 py-1.5 text-xs text-muted-foreground hover:bg-muted transition-colors"
          >
            加载更多（{digests.length - visibleCount} 条）
          </button>
        </div>
      )}
    </div>
  );
}

/* ───── Main ───── */
export function News() {
  const { t } = useI18n();
  const [tab, setTab] = useState<Tab>("home");

  const tabs: { key: Tab; label: string }[] = [
    { key: "home", label: "概览" },
    { key: "feed", label: "新闻流" },
    { key: "digests", label: "每日摘要" },
  ];

  return (
    <div className="mx-auto flex max-w-5xl flex-col p-6 h-full">
      {/* Header */}
      <div className="mb-4 flex items-center gap-2 shrink-0">
        <Newspaper className="h-5 w-5 text-primary" />
        <h1 className="text-lg font-semibold">{t.news}</h1>
      </div>

      {/* Tab bar */}
      <div className="mb-5 flex gap-1 border-b shrink-0">
        {tabs.map((tb) => (
          <button
            key={tb.key}
            onClick={() => setTab(tb.key)}
            className={cn(
              "px-4 py-2 text-sm font-medium border-b-2 transition-colors -mb-px",
              tab === tb.key
                ? "border-primary text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground",
            )}
          >
            {tb.label}
          </button>
        ))}
      </div>

      {/* Tab content — internal scroll */}
      <div className="flex-1 min-h-0 overflow-y-auto">
        {tab === "home" && <NewsHome />}
        {tab === "feed" && (
          <div className="flex-1 min-h-0">
            <NewsFeed />
          </div>
        )}
        {tab === "digests" && <NewsDigests />}
      </div>
    </div>
  );
}
