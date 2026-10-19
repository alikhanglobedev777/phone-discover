import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  activeFilterSummary, catalogStatus, converse, conversationPayload, forgetConversation, formatPriceRange, safeSourceUrl, searchProviderLabel,
} from "../lib/pakistan";
import type { ConversationRequest, LocalResult, ResearchPreview, AIGuidance } from "../lib/pakistan";

type Props = {
  onOpenDevice: (slug: string) => void;
  onCompareDevice: (slug: string) => void;
};

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  text: string;
  results?: LocalResult[];
  needsResearch?: boolean;
  research?: ResearchPreview;
  guidance?: AIGuidance;
  memoryUsed?: boolean;
  filters?: string;
  references?: { results: LocalResult[]; notice: string };
};

type EditableFilters = Partial<Omit<ConversationRequest, "session_id" | "message" | "research" | "guidance">>;

const PRIORITIES = ["camera", "gaming", "battery", "display", "value"];
const QUICK_PROMPTS = [
  "Lahore mein 80 hazar tak used PTA approved gaming phone",
  "Best box pack camera phone under 120k in Karachi",
  "Samsung mein batao",
];

function uuid() {
  // Modern browsers support secure UUID generation. The server uses this
  // bearer token to isolate sessions; never persist it in localStorage/URLs.
  return crypto.randomUUID();
}

const GREETING: ChatMessage = {
  id: "welcome", role: "assistant",
  text: "Hi! What phone can I help you find?",
};

function PriceCard({ result, onOpenDevice, onCompareDevice }: {
  result: LocalResult;
  onOpenDevice: Props["onOpenDevice"];
  onCompareDevice: Props["onCompareDevice"];
}) {
  const { device, variant, market_price: price } = result;
  const sourceUrl = safeSourceUrl(price.source_url);
  return (
    <article className="pk-result-card">
      <div className="pk-result-head">
        {device.primary_image_url ? <img src={device.primary_image_url} alt="" loading="lazy" /> : <span className="pk-phone-placeholder" aria-hidden="true">▣</span>}
        <div>
          <span className="pk-kicker">{device.brand} · {variant.ram_gb} GB / {variant.storage_gb} GB</span>
          <h3>{device.name}</h3>
          <p className="pk-result-price">{formatPriceRange(price)}</p>
        </div>
      </div>
      <p className="pk-result-meta">{price.condition.replaceAll("_", " ")} · {price.pta_status.replaceAll("_", " ")} · {price.city || "Pakistan"}</p>
      {price.evidence_type === "web_researched" && <p className="pk-evidence-note"><strong>Web researched · saved to catalog</strong>. Source-reported facts awaiting independent review.</p>}
      <p className="pk-evidence-note">PTA: {price.pta_verification === "checked" ? "independently checked evidence" : "reported or not independently checked"}. Observed {new Date(price.observed_at).toLocaleDateString("en-PK")}; asking price, not a live offer.</p>
      {result.fit_score !== null && <p className="pk-evidence-note">Editorial fit: {result.fit_score.toFixed(0)}/100 (not a probability or independent benchmark)</p>}
      {result.strengths.length > 0 && <p className="pk-result-meta">{result.strengths.join(" · ")}</p>}
      {result.tradeoffs.length > 0 && <p className="pk-evidence-note">Consider: {result.tradeoffs.join(" · ")}</p>}
      <div className="pk-result-actions">
        {sourceUrl && <a href={sourceUrl} target="_blank" rel="noopener noreferrer">Price source</a>}
        <button type="button" onClick={() => onOpenDevice(device.slug)} aria-label={`View details for ${device.name}`}>Details</button>
        <button type="button" onClick={() => onCompareDevice(device.slug)} aria-label={`Add ${device.name} to comparison`}>+ Compare</button>
      </div>
    </article>
  );
}

export function RecommendationAssistant({ onOpenDevice, onCompareDevice }: Props) {
  const queryClient = useQueryClient();
  const status = useQuery({ queryKey: ["catalog-status"], queryFn: catalogStatus, staleTime: 30_000 });
  const researchAvailable = status.data?.research_available === true;
  const [sessionId, setSessionId] = useState(uuid);
  const [message, setMessage] = useState("");
  const [budget, setBudget] = useState("");
  const [city, setCity] = useState("");
  const [condition, setCondition] = useState("");
  const [ptaStatus, setPtaStatus] = useState("");
  const [ptaVerification, setPtaVerification] = useState("");
  const [priorities, setPriorities] = useState<string[]>([]);
  const [ramMin, setRamMin] = useState("");
  const [storageMin, setStorageMin] = useState("");
  const [strictBudget, setStrictBudget] = useState(true);
  const [researchEnabled, setResearchEnabled] = useState(false);
  const [guidanceEnabled, setGuidanceEnabled] = useState(false);
  const [pending, setPending] = useState<EditableFilters>({});
  const [messages, setMessages] = useState<ChatMessage[]>([GREETING]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const requestRef = useRef<AbortController | null>(null);
  const chatStreamRef = useRef<HTMLDivElement | null>(null);
  const formRef = useRef<HTMLFormElement | null>(null);
  const generationRef = useRef(0);

  useEffect(() => {
    const stream = chatStreamRef.current;
    if (stream) stream.scrollTop = stream.scrollHeight;
  }, [messages, loading]);

  useEffect(() => () => {
    generationRef.current += 1;
    requestRef.current?.abort();
  }, []);

  function change<K extends keyof EditableFilters>(key: K, value: EditableFilters[K]) {
    setPending((current) => ({ ...current, [key]: value }));
  }

  function togglePriority(value: string) {
    const next = priorities.includes(value) ? priorities.filter((entry) => entry !== value) : [...priorities, value];
    setPriorities(next);
    change("priorities", next);
  }

  function syncControls(criteria: Record<string, unknown>) {
    setBudget(String(criteria.budget_pkr ?? ""));
    setCity(String(criteria.city ?? ""));
    setCondition(String(criteria.condition ?? ""));
    setPtaStatus(String(criteria.pta_status ?? ""));
    setPtaVerification(String(criteria.pta_verification ?? ""));
    setRamMin(String(criteria.ram_min ?? ""));
    setStorageMin(String(criteria.storage_min ?? ""));
    setPriorities(Array.isArray(criteria.priorities) ? criteria.priorities as string[] : []);
    setStrictBudget(criteria.strict_budget !== false);
  }

  function choosePrompt(prompt: string, index: number) {
    setMessage(prompt);
    // Complete examples start a new search; the brand-only example is a follow-up.
    if (index < 2) {
      syncControls({});
      setPending({ reset_context: true });
    }
  }

  async function newChat() {
    generationRef.current += 1;
    requestRef.current?.abort();
    requestRef.current = null;
    const previousId = sessionId;
    setSessionId(uuid());
    setMessages([{ ...GREETING, id: uuid() }]);
    setMessage("");
    setBudget(""); setCity(""); setCondition(""); setPtaStatus("");
    setPtaVerification(""); setPriorities([]); setRamMin(""); setStorageMin("");
    setStrictBudget(true); setResearchEnabled(false); setGuidanceEnabled(false); setPending({});
    setLoading(false); setError("");
    try {
      await forgetConversation(previousId);
    } catch (reason) {
      setError(reason instanceof Error ? `${reason.message} Your new chat uses a separate session; old data expires under the server retention policy.` : "Previous session may still be stored on the server.");
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = message.trim();
    if (!text) { setError("Please enter a request, including your preferred phone features."); return; }
    if (loading) return;
    setError("");
    setLoading(true);
    const generation = generationRef.current;
    const controller = new AbortController();
    requestRef.current = controller;
    const explicit = { ...pending };
    const userMessage: ChatMessage = { id: uuid(), role: "user", text };
    setMessages((current) => [...current, userMessage]);
    setMessage("");
    try {
      const response = await converse(conversationPayload(sessionId, text, researchEnabled && researchAvailable, explicit, guidanceEnabled), controller.signal);
      if (generation !== generationRef.current) return;
      setPending({});
      syncControls(response.criteria);
      if (response.catalog_updated) {
        void Promise.all(["devices", "brands", "pakistan-market", "catalog-status", "device"].map((key) =>
          queryClient.invalidateQueries({ queryKey: [key] })));
      }
      setMessages((current) => [...current, {
        id: response.query_id || uuid(), role: "assistant", text: response.explanation,
        results: response.results, needsResearch: response.needs_research,
        research: response.research, guidance: response.guidance, memoryUsed: response.memory_used,
        filters: activeFilterSummary(response.criteria), references: response.research.results?.length ? undefined : response.price_references,
      }]);
    } catch (reason) {
      if (generation !== generationRef.current || (reason instanceof Error && reason.name === "AbortError")) return;
      setError(reason instanceof Error ? reason.message : "The search could not be completed.");
      setMessage(text); // Preserve the text for retry; pending controls are intact.
      setMessages((current) => current.filter((entry) => entry.id !== userMessage.id));
    } finally {
      if (generation === generationRef.current) {
        requestRef.current = null;
        setLoading(false);
      }
    }
  }

  return (
    <section className="assistant-card assistant-workspace" id="assistant" aria-labelledby="assistant-title">
      <header className="assistant-header">
        <h2 id="assistant-title">Chat</h2>
        <button type="button" className="assistant-new-chat" onClick={() => void newChat()} aria-label="Start a new chat and clear this session's preferences">New chat</button>
      </header>
      <div className="assistant-layout">
        <details className="assistant-preferences">
          <summary><span>Preferences</span><span className="preferences-chevron" aria-hidden="true">⌄</span></summary>
          <aside className="assistant-requirements" aria-label="Recommendation preferences">
          <div className="assistant-control">
            <span className="assistant-control-label">What matters most?</span>
            <div className="priority-grid">
              {PRIORITIES.map((value) => <button key={value} type="button" disabled={loading} className={priorities.includes(value) ? "active" : ""} aria-pressed={priorities.includes(value)} onClick={() => togglePriority(value)}>{value}</button>)}
            </div>
          </div>
          <div className="assistant-two-fields">
            <label className="assistant-field"><span>Maximum budget (PKR)</span>
              <div className="budget-input"><b>₨</b><input disabled={loading} type="number" min="1" max="999999999" value={budget} placeholder="80000" onChange={(event) => { const value = event.target.value; setBudget(value); if (value) change("budget_pkr", value); else change("budget_pkr", null); }} /></div>
            </label>
            <label className="assistant-field"><span>City</span><input disabled={loading} type="text" maxLength={100} value={city} placeholder="Lahore" onChange={(event) => { setCity(event.target.value); if (event.target.value.trim()) change("city", event.target.value.trim()); else change("city", null); }} /></label>
          </div>
          <div className="assistant-two-fields">
            <label className="assistant-field"><span>Condition</span><select disabled={loading} value={condition} onChange={(event) => { setCondition(event.target.value); if (event.target.value) change("condition", event.target.value); else change("condition", null); }}><option value="">From message / any</option><option value="box_pack">New / box pack</option><option value="open_box">Open box</option><option value="used">Used</option><option value="refurbished">Refurbished</option></select></label>
            <label className="assistant-field"><span>PTA status</span><select disabled={loading} value={ptaStatus} onChange={(event) => { setPtaStatus(event.target.value); if (event.target.value) change("pta_status", event.target.value); else change("pta_status", null); }}><option value="">From message / any</option><option value="approved">PTA approved (reported or checked)</option><option value="non_pta">Non-PTA</option><option value="cpid">CPID (not official approval)</option><option value="patched">Patched (not official approval)</option></select></label>
          </div>
          <label className="assistant-field"><span>PTA evidence requirement</span><select disabled={loading} value={ptaVerification} onChange={(event) => { setPtaVerification(event.target.value); if (event.target.value) change("pta_verification", event.target.value); else change("pta_verification", null); }}><option value="">Any available evidence</option><option value="reported">Seller/source reported</option><option value="checked">Independently checked evidence</option></select></label>
          <div className="assistant-two-fields">
            <label className="assistant-field"><span>Minimum RAM</span><select disabled={loading} value={ramMin} onChange={(event) => { setRamMin(event.target.value); if (event.target.value) change("ram_min", Number(event.target.value)); else change("ram_min", null); }}><option value="">Any</option><option value="6">6 GB</option><option value="8">8 GB</option><option value="12">12 GB</option><option value="16">16 GB</option></select></label>
            <label className="assistant-field"><span>Minimum storage</span><select disabled={loading} value={storageMin} onChange={(event) => { setStorageMin(event.target.value); if (event.target.value) change("storage_min", Number(event.target.value)); else change("storage_min", null); }}><option value="">Any</option><option value="128">128 GB</option><option value="256">256 GB</option><option value="512">512 GB</option></select></label>
          </div>
          <label className="strict-budget-toggle"><input type="checkbox" disabled={loading} checked={strictBudget} onChange={(event) => { setStrictBudget(event.target.checked); change("strict_budget", event.target.checked); }} /><span><strong>Strict PKR budget</strong><small>Require observed upper price bound to fit</small></span></label>
          <label className="strict-budget-toggle"><input type="checkbox" disabled={loading || status.data?.guidance_available === false} checked={guidanceEnabled} onChange={(event) => setGuidanceEnabled(event.target.checked)} /><span><strong>Use AI general guidance</strong><small>{status.data?.guidance_available === false ? "Add a Gemini or OpenAI key to enable AI guidance. Search and catalog features still work." : `Uses ${status.data?.ai_provider || "the configured AI provider"} for general advice when no local matches exist. Prices and PTA claims remain unverified.`}</small></span></label>
          {status.data?.automatic_research ? <p className="pk-evidence-note"><strong>Automatic web research is on.</strong> Search provider: {searchProviderLabel(status.data.search_provider)}. Missing phones are researched and sourced results saved to the catalog.</p> : <label className="strict-budget-toggle"><input type="checkbox" disabled={loading || !researchAvailable} checked={researchEnabled && researchAvailable} onChange={(event) => setResearchEnabled(event.target.checked)} /><span><strong>Request web research</strong><small>{status.isError ? "Could not check web research availability." : status.isPending ? "Checking availability..." : researchAvailable ? "Search external sources with the configured provider." : "Web research is currently disabled or unconfigured."}</small></span></label>}
          {status.data?.configuration_error && <p className="pk-evidence-note" role="status">{status.data.configuration_error}</p>}
          <div className="quick-prompts"><span>Suggested questions</span>{QUICK_PROMPTS.map((prompt, index) => <button type="button" disabled={loading} key={prompt} onClick={() => choosePrompt(prompt, index)}>{prompt}</button>)}</div>
          </aside>
        </details>
        <div className="assistant-conversation">
          {status.isError && <p className="assistant-service-warning" role="status">Service temporarily unavailable. You can try again shortly.</p>}
          {status.data?.catalog_status === "empty" && <p className="state-message" role="status">The phone catalog is empty. Local recommendations will appear after phones and Pakistani prices are imported.</p>}
          {status.data?.catalog_status === "missing_prices" && <p className="state-message" role="status">Catalog phones are available, but their Pakistani price evidence needs adding or refreshing.</p>}
          <div className="chat-stream" ref={chatStreamRef} role="log" aria-label="Assistant conversation" aria-live="polite" aria-relevant="additions">
            {messages.map((entry) => <div className={`chat-message chat-${entry.role}`} key={entry.id}>
              <div className="chat-avatar">{entry.role === "assistant" ? "PD" : "You"}</div>
              <div className="chat-bubble">
                <p>{entry.text}</p>
                {entry.memoryUsed && <p className="pk-evidence-note">Preferences carried forward from this session.</p>}
                {entry.filters && <p className="pk-evidence-note">Filters used — {entry.filters}</p>}
                {!!entry.references?.results.length && <section className="pk-reference-results" aria-label="Price references with unconfirmed city or PTA status"><h3>Price references — city/PTA unconfirmed</h3><p className="pk-evidence-note">{entry.references.notice}</p><div className="pk-result-grid">{entry.references.results.map((result) => <PriceCard key={`${entry.id}-reference-${result.device.slug}`} result={result} onOpenDevice={onOpenDevice} onCompareDevice={onCompareDevice} />)}</div></section>}
                {entry.results && entry.results.length > 0 && <div className="pk-result-grid">{entry.results.map((result) => <PriceCard key={`${entry.id}-${result.device.slug}`} result={result} onOpenDevice={onOpenDevice} onCompareDevice={onCompareDevice} />)}</div>}
                {entry.needsResearch && researchAvailable && !status.data?.automatic_research && <p className="pk-evidence-note">Local evidence is incomplete. You can request web research for source-linked details.</p>}
                {entry.guidance?.status === "generated" && <div className="pk-research-preview pk-guidance-preview"><strong>AI general guidance · not verified</strong><p>{entry.guidance.notice}</p><p className="pk-research-summary">{entry.guidance.text}</p></div>}
                {entry.guidance && ["unavailable", "disabled", "rate_limited"].includes(entry.guidance.status) && <p className="pk-evidence-note" role="status">AI guidance: {entry.guidance.notice}</p>}
                {entry.research && entry.research.status !== "not_requested" && <div className="pk-research-preview"><strong>Web research: {entry.research.status.replaceAll("_", " ")}</strong><p>{entry.research.notice}</p>{entry.research.summary && <p className="pk-research-summary">{entry.research.summary}</p>}<div className="pk-result-grid">{entry.research.results?.filter((result) => !entry.results?.some((match) => match.device.slug === result.device.slug)).map((result) => <PriceCard key={`${entry.id}-web-${result.device.slug}`} result={result} onOpenDevice={onOpenDevice} onCompareDevice={onCompareDevice} />)}</div>{entry.research.sources?.length > 0 && <ul>{entry.research.sources.map((source) => { const url = safeSourceUrl(source.url); return url ? <li key={url}><a href={url} target="_blank" rel="noopener noreferrer">{source.title || "Research source"} ↗</a></li> : null; })}</ul>}</div>}
              </div>
            </div>)}
            {loading && <div className="chat-message chat-assistant"><div className="chat-avatar">PD</div><div className="chat-bubble" role="status">{status.data?.automatic_research ? "Checking the catalog, then researching the web if needed. This may take a minute…" : "Checking published devices and eligible price observations…"}</div></div>}
          </div>
          <form className="assistant-composer" ref={formRef} onSubmit={(event) => void submit(event)}>
            <label htmlFor="pk-chat-message" className="assistant-sr-only">Message the phone assistant</label>
            <div className="assistant-compose-row">
              <textarea id="pk-chat-message" maxLength={1000} disabled={loading} value={message} onChange={(event) => setMessage(event.target.value)} onKeyDown={(event) => { if ((event.ctrlKey || event.metaKey) && event.key === "Enter") { event.preventDefault(); formRef.current?.requestSubmit(); } }} placeholder="Ask about a phone, budget or PTA status…" rows={2} />
              <button type="submit" disabled={loading || !message.trim()} aria-label={loading ? "Searching for phones" : "Send message"}>{loading ? "…" : "Send ↗"}</button>
            </div>
            {error && <p className="assistant-input-error" role="alert">{error}</p>}
          </form>
        </div>
      </div>
    </section>
  );
}
