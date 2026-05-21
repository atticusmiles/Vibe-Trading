import { authHeaders, withAuthQuery } from "@/lib/apiAuth";

const BASE = "";

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export const AUTH_REQUIRED_MESSAGE =
  "Authentication required. Please log in.";

export function isAuthRequiredError(error: unknown): boolean {
  return error instanceof ApiError && (error.status === 401 || error.status === 403);
}

let _handling401 = false;

function handle401(status: number) {
  if (status === 401 && !_handling401) {
    if (window.location.pathname === "/login") return;
    _handling401 = true;
    import("@/lib/apiAuth").then(({ clearApiAuthKey }) => {
      clearApiAuthKey();
      window.location.href = "/login";
    });
  }
}

async function errorFromResponse(res: Response): Promise<ApiError> {
  let detail = `HTTP ${res.status}`;
  try {
    const body = await res.json();
    detail = body.detail || body.message || detail;
  } catch { /* ignore */ }
  if (res.status === 401 || res.status === 403) {
    detail = AUTH_REQUIRED_MESSAGE;
  }
  return new ApiError(detail, res.status);
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const { headers, ...rest } = options ?? {};
  const mergedHeaders: Record<string, string> = { "Content-Type": "application/json", ...authHeaders() };
  if (headers) {
    new Headers(headers).forEach((value, key) => {
      mergedHeaders[key] = value;
    });
  }
  const res = await fetch(`${BASE}${path}`, {
    ...rest,
    headers: mergedHeaders,
  });
  if (!res.ok) {
    const err = await errorFromResponse(res);
    handle401(err.status);
    throw err;
  }
  const text = await res.text();
  try {
    return text ? JSON.parse(text) : ({} as T);
  } catch {
    throw new ApiError(`Invalid JSON response from ${path}`, res.status);
  }
}

export interface UploadResult {
  status: string;
  file_path: string;
  filename: string;
}

async function uploadFile(file: File): Promise<UploadResult> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/upload`, { method: "POST", headers: authHeaders(), body: form });
  if (!res.ok) {
    const err = await errorFromResponse(res);
    handle401(err.status);
    throw err;
  }
  return res.json();
}

export const api = {
  // Auth
  register: (username: string, password: string) =>
    request<{ id: number; username: string; created_at: string }>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  login: (username: string, password: string) =>
    request<{ access_token: string; token_type: string; expires_in: number }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  getMe: () =>
    request<{ id: number; username: string; preferences: Record<string, unknown>; created_at: string }>("/auth/me"),
  changePassword: (old_password: string, new_password: string) =>
    request<{ detail: string }>("/auth/password", {
      method: "PUT",
      body: JSON.stringify({ old_password, new_password }),
    }),

  // User config
  getPreferences: () => request<Record<string, unknown>>("/api/user/settings/preferences"),
  updatePreferences: (prefs: Record<string, unknown>) =>
    request<{ detail: string }>("/api/user/settings/preferences", { method: "PUT", body: JSON.stringify(prefs) }),
  getSettings: () => request<Record<string, unknown>>("/api/user/settings/system"),
  updateSettings: (settings: Record<string, unknown>) =>
    request<{ detail: string }>("/api/user/settings/system", { method: "PUT", body: JSON.stringify(settings) }),

  uploadFile,
  computeCorrelation: (codes: string, days: number, method: string) =>
    request<{ labels: string[]; matrix: number[][] }>(`/correlation?codes=${encodeURIComponent(codes)}&days=${days}&method=${method}`),
  listRuns: () => request<RunListItem[]>("/runs"),
  getRun: (id: string) => request<RunData>(`/runs/${id}`),
  getRunCode: (id: string) => request<Record<string, string>>(`/runs/${id}/code`),
  getRunPine: (id: string) => request<PineScriptResult>(`/runs/${id}/pine`),
  listSessions: () => request<SessionItem[]>("/sessions"),
  createSession: (title?: string) => request<SessionItem>("/sessions", { method: "POST", body: JSON.stringify({ title: title || "" }) }),
  deleteSession: (sid: string) => request<{ status: string }>(`/sessions/${sid}`, { method: "DELETE" }),
  renameSession: (sid: string, title: string) => request<{ status: string }>(`/sessions/${sid}`, { method: "PATCH", body: JSON.stringify({ title }) }),
  sendMessage: (sid: string, content: string) => request<{ message_id: string; attempt_id: string }>(`/sessions/${sid}/messages`, { method: "POST", body: JSON.stringify({ content }) }),
  cancelSession: (sid: string) => request<{ status: string }>(`/sessions/${sid}/cancel`, { method: "POST" }),
  getSessionMessages: (sid: string) => request<MessageItem[]>(`/sessions/${sid}/messages`),
  sseUrl: (sid: string) => withAuthQuery(`${BASE}/sessions/${sid}/events`),

  // Swarm API
  listSwarmPresets: () => request<SwarmPreset[]>("/swarm/presets"),
  createSwarmRun: (preset_name: string, user_vars: Record<string, string>) =>
    request<{ id: string; status: string }>("/swarm/runs", {
      method: "POST",
      body: JSON.stringify({ preset_name, user_vars }),
    }),
  listSwarmRuns: () => request<SwarmRunSummary[]>("/swarm/runs"),
  getSwarmRun: (id: string) => request<Record<string, unknown>>(`/swarm/runs/${id}`),
  swarmSseUrl: (id: string) => withAuthQuery(`${BASE}/swarm/runs/${id}/events`),
  cancelSwarmRun: (id: string) =>
    request<{ status: string }>(`/swarm/runs/${id}/cancel`, { method: "POST" }),

  // Fact Tables
  listTrends: (status?: string) =>
    request<TrendItem[]>(`/api/trends${status ? `?status=${status}` : ""}`),
  getTrend: (id: number) => request<TrendItem>(`/api/trends/${id}`),
  createTrend: (data: { title: string; level?: string; confidence?: number; evidence?: string }) =>
    request<TrendItem>("/api/trends", { method: "POST", body: JSON.stringify(data) }),
  updateTrend: (id: number, data: Partial<TrendItem>) =>
    request<TrendItem>(`/api/trends/${id}`, { method: "PUT", body: JSON.stringify(data) }),
  deleteTrend: (id: number) => request<{ id: number; status: string }>(`/api/trends/${id}`, { method: "DELETE" }),

  listIndustries: (status?: string) =>
    request<IndustryItem[]>(`/api/industries${status ? `?status=${status}` : ""}`),
  getIndustry: (id: number) => request<IndustryItem>(`/api/industries/${id}`),
  createIndustry: (data: { name: string; confidence?: number; reason?: string; research_report?: string; recommended_stocks?: string[] }) =>
    request<IndustryItem>("/api/industries", { method: "POST", body: JSON.stringify(data) }),
  updateIndustry: (id: number, data: Partial<IndustryItem>) =>
    request<IndustryItem>(`/api/industries/${id}`, { method: "PUT", body: JSON.stringify(data) }),
  deleteIndustry: (id: number) => request<{ id: number; status: string }>(`/api/industries/${id}`, { method: "DELETE" }),

  listStocks: (status?: string) =>
    request<StockItem[]>(`/api/stocks${status ? `?status=${status}` : ""}`),
  getStock: (id: number) => request<StockItem>(`/api/stocks/${id}`),
  createStock: (data: { name: string; code: string; confidence?: number; industry_name?: string; position?: number; advice?: string; target_price?: number; stop_loss?: number; reason?: string }) =>
    request<StockItem>("/api/stocks", { method: "POST", body: JSON.stringify(data) }),
  updateStock: (id: number, data: Partial<StockItem>) =>
    request<StockItem>(`/api/stocks/${id}`, { method: "PUT", body: JSON.stringify(data) }),
  deleteStock: (id: number) => request<{ id: number; status: string }>(`/api/stocks/${id}`, { method: "DELETE" }),

  getDashboard: () => request<DashboardData>("/api/dashboard"),

  // Proposals
  listProposals: (params?: { type?: string; status?: string; target_id?: number; since?: string; page?: number; per_page?: number }) => {
    const qs = new URLSearchParams();
    if (params?.type) qs.set("type", params.type);
    if (params?.status) qs.set("status", params.status);
    if (params?.target_id != null) qs.set("target_id", String(params.target_id));
    if (params?.since) qs.set("since", params.since);
    if (params?.page) qs.set("page", String(params.page));
    if (params?.per_page) qs.set("per_page", String(params.per_page));
    const query = qs.toString();
    return request<ProposalListResponse>(`/api/proposals${query ? `?${query}` : ""}`);
  },
  getProposal: (id: number) => request<ProposalItem>(`/api/proposals/${id}`),
  createProposal: (data: {
    target_type: string; action: string; target_id?: number;
    title: string; summary?: string; confidence?: number;
    payload: string; run_id?: string; source_agent?: string;
  }) => request<ProposalItem>("/api/proposals", { method: "POST", body: JSON.stringify(data) }),
  adoptProposal: (id: number) => request<ProposalItem>(`/api/proposals/${id}/adopt`, { method: "POST" }),
  rejectProposal: (id: number) => request<ProposalItem>(`/api/proposals/${id}/reject`, { method: "POST" }),
  cancelProposal: (id: number) => request<ProposalItem>(`/api/proposals/${id}/cancel`, { method: "POST" }),

  // News
  listNewsDigests: (params?: { start_date?: string; end_date?: string }) =>
    request<NewsDigestItem[]>("/api/news/digests" + (params ? "?" + new URLSearchParams(Object.entries(params).filter(([, v]) => v).map(([k, v]) => [k, v!])).toString() : "")),
  getLatestDigest: () => request<NewsDigestItem>("/api/news/digests/latest"),
  getDigestDetail: (id: number) => request<NewsDigestItem>(`/api/news/digests/${id}`),
  triggerDigest: (target_date?: string) =>
    request<NewsDigestItem>("/api/news/digests/trigger" + (target_date ? `?target_date=${target_date}` : ""), { method: "POST" }),
  listRecentNews: (params?: { limit?: number }) =>
    request<NewsItem[]>("/api/news/recent" + (params?.limit ? `?limit=${params.limit}` : "")),

  // Candidates
  listCandidates: (params?: { target_type?: string; candidate_status?: string; page?: number; per_page?: number }) => {
    const qs = new URLSearchParams();
    if (params?.target_type) qs.set("target_type", params.target_type);
    if (params?.candidate_status) qs.set("status", params.candidate_status);
    if (params?.page) qs.set("page", String(params.page));
    if (params?.per_page) qs.set("per_page", String(params.per_page));
    const query = qs.toString();
    return request<CandidateListResponse>(`/api/research/candidates${query ? `?${query}` : ""}`);
  },
  getCandidate: (id: number) => request<CandidateResponse>(`/api/research/candidates/${id}`),
  batchResearch: (candidate_ids: number[], max_concurrent = 2) =>
    request<BatchResearchResponse>("/api/research/candidates/batch-research", {
      method: "POST",
      body: JSON.stringify({ candidate_ids, max_concurrent }),
    }),
  triggerScan: (target_type: "trends" | "industries" | "stocks") =>
    request<{ status: string; run_id: string }>(`/api/research/scan/${target_type}`, { method: "POST" }),
};

// --- Swarm types ---

export interface SwarmPreset {
  name: string;
  title: string;
  description: string;
  agent_count: number;
  variables: { name: string; description: string; required: boolean }[];
}

export interface SwarmRunSummary {
  id: string;
  preset_name: string;
  status: string;
  created_at: string;
  task_count: number;
  completed_count: number;
}

// --- Types matching backend API contracts ---

export interface RunListItem {
  run_id: string;
  status: string;
  created_at: string;
  prompt?: string;
  total_return?: number;
  sharpe?: number;
  codes?: string[];
  start_date?: string;
  end_date?: string;
}

export interface PriceBar {
  time: string;
  timestamp?: string;
  code?: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface TradeMarker {
  time: string;
  timestamp?: string;
  code?: string;
  side: "BUY" | "SELL";
  price: number;
  qty?: number;
  reason?: string;
  text?: string;
}

export interface EquityPoint {
  time: string;
  equity: string | number;
  drawdown: string | number;
}

export interface ValidationData {
  monte_carlo?: {
    actual_sharpe: number;
    actual_max_dd: number;
    p_value_sharpe: number;
    p_value_max_dd: number;
    simulated_sharpe_mean: number;
    simulated_sharpe_std: number;
    simulated_sharpe_p5: number;
    simulated_sharpe_p95: number;
    n_simulations: number;
    n_trades: number;
    error?: string;
  };
  bootstrap?: {
    observed_sharpe: number;
    ci_lower: number;
    ci_upper: number;
    median_sharpe: number;
    prob_positive: number;
    confidence: number;
    n_bootstrap: number;
    error?: string;
  };
  walk_forward?: {
    n_windows: number;
    windows: Array<{
      window: number;
      start: string;
      end: string;
      return: number;
      sharpe: number;
      max_dd: number;
      trades: number;
      win_rate: number;
    }>;
    profitable_windows: number;
    consistency_rate: number;
    return_mean: number;
    return_std: number;
    sharpe_mean: number;
    sharpe_std: number;
    error?: string;
  };
}

export interface RunData {
  status: string;
  run_id: string;
  prompt?: string;
  elapsed_seconds?: number;
  run_directory?: string;
  run_stage?: string;
  run_context?: Record<string, unknown>;

  metrics?: BacktestMetrics;
  artifacts?: ArtifactInfo[];
  validation?: ValidationData;

  price_series?: Record<string, PriceBar[]>;
  indicator_series?: Record<string, Record<string, IndicatorPoint[]>>;
  trade_markers?: TradeMarker[];
  equity_curve?: EquityPoint[];
  trade_log?: Array<Record<string, string>>;
  run_logs?: Array<{ source?: string; line_number?: number; message?: string }>;
}

export interface BacktestMetrics {
  final_value: number;
  total_return: number;
  annual_return: number;
  max_drawdown: number;
  sharpe: number;
  win_rate: number;
  trade_count: number;
  [key: string]: number;
}


export interface IndicatorPoint {
  time: string;
  value: number;
}

export interface ArtifactInfo {
  name: string;
  path: string;
  type: string;
  size: number;
  exists: boolean;
}

export interface PineScriptResult {
  exists: boolean;
  content: string | null;
}

export interface SessionItem {
  session_id: string;
  title?: string;
  status?: string;
  created_at?: string;
  updated_at?: string;
  last_attempt_id?: string;
}

export interface MessageItem {
  message_id: string;
  session_id: string;
  role: string;
  content: string;
  created_at: string;
  linked_attempt_id?: string;
  metadata?: Record<string, unknown>;
}

// --- Fact Table types ---

export interface TrendItem {
  id: number;
  user_id: number;
  status: string;
  title: string;
  level: string | null;
  confidence: number;
  evidence: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface IndustryItem {
  id: number;
  user_id: number;
  status: string;
  name: string;
  confidence: number;
  reason: string | null;
  research_report: string | null;
  recommended_stocks: string;
  recommended_count: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface StockItem {
  id: number;
  user_id: number;
  status: string;
  name: string;
  code: string;
  confidence: number;
  industry_name: string | null;
  position: number | null;
  advice: string | null;
  target_price: number | null;
  stop_loss: number | null;
  reason: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface RecentlyUpdatedItem {
  type: "trend" | "industry" | "stock";
  id: number;
  title: string;
  confidence: number;
  updated_at: string | null;
}

export interface DashboardData {
  stats: {
    trends: Record<string, number>;
    industries: Record<string, number>;
    stocks: Record<string, number>;
  };
  recently_updated: RecentlyUpdatedItem[];
  latest_runs: Array<{ run_id: string }>;
  pending_proposals: Record<string, number>;
}

// --- Proposal types ---

export interface ProposalItem {
  id: number;
  user_id: number;
  target_type: "trend" | "industry" | "stock";
  target_id: number;
  action: "create" | "update" | "delete";
  status: "pending" | "adopted" | "rejected";
  title: string;
  summary: string | null;
  confidence: number;
  payload: string;
  original_payload: string | null;
  run_id: string | null;
  source_agent: string | null;
  created_at: string | null;
  reviewed_at: string | null;
}

export interface ProposalListResponse {
  items: ProposalItem[];
  total: number;
  page: number;
  per_page: number;
}

// --- News types ---

export interface NewsDigestItem {
  id: number;
  user_id: number;
  digest_date: string;
  content: string;
  summary: string | null;
  created_at: string;
}

export interface NewsItem {
  id: number;
  source_id: string;
  title: string;
  content: string | null;
  level: string | null;
  source: string;
  published_at: string;
}

// --- Candidate types ---

export interface CandidateResponse {
  id: number;
  target_type: "trend" | "industry" | "stock";
  name: string;
  code: string | null;
  source_context: string | null;
  initial_score: number;
  status: string;
  source_run_id: string | null;
  research_run_id: string | null;
  report: string | null;
  report_type: string | null;
  reported_at: string | null;
  extra_reports: string;
  conclusion: string | null;
  proposal_id: number | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface CandidateListResponse {
  items: CandidateResponse[];
  total: number;
  page: number;
  per_page: number;
}

export interface BatchResearchResponse {
  runs: Array<{ run_id: string; candidate_id: number; candidate_name: string; status: string; error?: string }>;
  total: number;
  skipped: number;
}
