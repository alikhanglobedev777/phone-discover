/** Pakistan-only, read-only public API clients. All prices are observed PKR ranges. */
export type MarketPrice = {
  currency: "PKR";
  condition: string;
  grade: string;
  pta_status: string;
  pta_verification: string;
  city: string;
  observed_min_pkr: string;
  observed_max_pkr: string;
  observed_at: string;
  source_url: string | null;
  evidence_type: string;
  availability: string;
  budget_fit: string | null;
};

export type LocalVariant = {
  id: number;
  name: string;
  ram_gb: number;
  storage_gb: number;
  chipset: string;
  camera_score: string;
  gaming_score: string;
  battery_score: string;
};

export type LocalDevice = {
  id: number;
  slug: string;
  name: string;
  brand: string;
  summary: string;
  status: string;
  primary_image_url: string;
  detail_url: string;
};

export type LocalResult = {
  rank: number;
  recommended: boolean;
  device: LocalDevice;
  variant: LocalVariant;
  market_price: MarketPrice;
  fit_score: number | null;
  fit_score_is_probability: false;
  strengths: string[];
  tradeoffs: string[];
  missing_score_evidence: string[];
};

export type GeminiGuidance = {
  status: "not_requested" | "not_needed" | "disabled" | "rate_limited" | "unavailable" | "generated";
  text: string;
  notice: string;
};

export type ResearchPreview = {
  status: string;
  summary: string;
  sources: { url: string; title: string }[];
  notice: string;
};

export type ConversationRequest = {
  session_id: string;
  message: string;
  research: boolean;
  guidance: boolean;
  budget_pkr?: string;
  condition?: string;
  pta_status?: string;
  pta_verification?: string;
  city?: string;
  priorities?: string[];
  ram_min?: number;
  storage_min?: number;
  strict_budget?: boolean;
};

export type ConversationResponse = {
  session_id: string;
  query_id: string;
  criteria: Record<string, unknown>;
  memory_used: boolean;
  explanation: string;
  results: LocalResult[];
  count: number;
  needs_research: boolean;
  research_reason: string | null;
  research_executed: boolean;
  research: ResearchPreview;
  guidance: GeminiGuidance;
};

export type MarketSearchFilters = {
  q: string;
  city: string;
  condition: string;
  pta_status: string;
  pta_verification: string;
  budget_pkr: string;
  ram_min: string;
  sort: string;
};

export type MarketSearchResult = {
  slug: string;
  id: number;
  name: string;
  brand: { name: string; slug: string };
  status: string;
  summary: string;
  primary_image_url: string;
  variant: LocalVariant;
  price_observation: MarketPrice;
};

export type MarketSearchResponse = {
  count: number;
  page: number;
  page_size: number;
  has_more: boolean;
  needs_research: boolean;
  research_reason: string | null;
  price_disclaimer: string;
  results: MarketSearchResult[];
};

export function formatPkr(amount: string | number): string {
  const parsed = Number(amount);
  return Number.isFinite(parsed) && parsed >= 0
    ? `PKR ${new Intl.NumberFormat("en-PK", { maximumFractionDigits: 0 }).format(parsed)}`
    : "PKR price unavailable";
}

export function formatPriceRange(price: MarketPrice): string {
  const min = formatPkr(price.observed_min_pkr);
  const max = formatPkr(price.observed_max_pkr);
  return price.observed_min_pkr === price.observed_max_pkr ? min : `${min} – ${max}`;
}

/** Reject unsafe, local, credentialed, or non-HTTPS destinations from external research. */
export function safeSourceUrl(value: unknown): string | null {
  if (typeof value !== "string" || value.length > 1500) return null;
  try {
    const url = new URL(value);
    const host = url.hostname.toLowerCase();
    if (url.protocol !== "https:" || url.username || url.password || !host || url.port) return null;
    if (host === "localhost" || host.endsWith(".localhost") || host.endsWith(".local") || host.endsWith(".internal")) return null;
    // Public source links must be domain names, not private-network or raw IP destinations.
    if (!/^[a-z0-9-]+(?:\.[a-z0-9-]+)+$/.test(host) || /^\d+(?:\.\d+){3}$/.test(host)) return null;
    return url.toString();
  } catch {
    return null;
  }
}

export function marketQuery(filters: MarketSearchFilters, page: number): string {
  const params = new URLSearchParams({ require_price: "true", page: String(page), page_size: "9" });
  for (const [key, value] of Object.entries(filters)) {
    if (value.trim()) params.set(key, value.trim());
  }
  return params.toString();
}

export function conversationPayload(
  sessionId: string,
  message: string,
  research: boolean,
  pending: Partial<Omit<ConversationRequest, "session_id" | "message" | "research" | "guidance">>,
  guidance = false,
): ConversationRequest {
  // Do not retransmit defaults (or stale controls) on later turns: the server
  // merges only newly explicit fields into existing session preferences.
  return { session_id: sessionId, message: message.trim(), research, guidance, ...pending };
}

function csrfHeaders(): Record<string, string> {
  // Logged-in Django admin users use session authentication, which enforces CSRF.
  // Anonymous public requests work without a token.
  if (typeof document === "undefined") return {};
  const cookie = document.cookie.split("; ").find((part) => part.startsWith("csrftoken="));
  if (!cookie) return {};
  try { return { "X-CSRFToken": decodeURIComponent(cookie.slice("csrftoken=".length)) }; }
  catch { return {}; }
}

async function jsonApi<T>(path: string, options: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, { ...options, headers: { ...csrfHeaders(), ...options.headers }, credentials: "same-origin", cache: "no-store" });
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") throw error;
    throw new Error("Cannot reach Phone Discover. Check that the Django backend is running.");
  }
  if (!response.ok) {
    if (response.status === 429) throw new Error("Too many requests. Please try again later.");
    if (response.status === 503) throw new Error("Research or database service is unavailable. Try local search later.");
    let detail = "Please check your requirements and try again.";
    try {
      const body: unknown = await response.json();
      if (body && typeof body === "object" && "detail" in body && typeof body.detail === "string") {
        detail = body.detail.slice(0, 240);
      } else if (body && typeof body === "object" && "message" in body && typeof body.message === "string") {
        detail = body.message.slice(0, 240);
      }
    } catch { /* No JSON error body. */ }
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

export function searchPakistaniMarket(filters: MarketSearchFilters, page = 1): Promise<MarketSearchResponse> {
  return jsonApi(`/api/catalog/search/?${marketQuery(filters, page)}`);
}

export function converse(request: ConversationRequest, signal?: AbortSignal): Promise<ConversationResponse> {
  return jsonApi("/api/recommendations/converse/", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request), signal,
  });
}

export async function forgetConversation(sessionId: string): Promise<void> {
  // Do not expose the opaque bearer UUID in a query string or browser storage.
  const response = await fetch(`/api/recommendations/conversation/${encodeURIComponent(sessionId)}/`, {
    method: "DELETE", headers: csrfHeaders(), credentials: "same-origin", cache: "no-store",
  });
  if (!response.ok) throw new Error("The saved conversation could not be cleared on the server.");
}
