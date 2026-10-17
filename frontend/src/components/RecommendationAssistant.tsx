import { useRef, useState } from "react";
import type { FormEvent } from "react";
import {
  converse, conversationPayload, forgetConversation, formatPriceRange, safeSourceUrl,
} from "../lib/pakistan";
import type { ConversationRequest, LocalResult, ResearchPreview, GeminiGuidance } from "../lib/pakistan";

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
  guidance?: GeminiGuidance;
  memoryUsed?: boolean;
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
  text: "Assalam-o-alaikum! Tell me your PKR budget, city, PTA requirement, and what matters most. I’ll check eligible local price evidence first.",
};

function PriceCard({ result, onOpenDevice, onCompareDevice }: {
  result: LocalResult;
  onOpenDevice: Props["onOpenDevice"];
  onCompareDevice: Props["onCompareDevice"];
}) {
  const { device, variant, market_price: price } = result;
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
      <p className="pk-evidence-note">PTA: {price.pta_verification === "checked" ? "independently checked evidence" : "reported or not independently checked"}. Observed {new Date(price.observed_at).toLocaleDateString("en-PK")}; asking price, not a live offer.</p>
      {result.fit_score !== null && <p className="pk-evidence-note">Editorial fit: {result.fit_score.toFixed(0)}/100 (not a probability or independent benchmark)</p>}
      {result.strengths.length > 0 && <p className="pk-result-meta">{result.strengths.join(" · ")}</p>}
      {result.tradeoffs.length > 0 && <p className="pk-evidence-note">Consider: {result.tradeoffs.join(" · ")}</p>}
      <div className="pk-result-actions">
        <button type="button" onClick={() => onOpenDevice(device.slug)}>Phone details</button>
        <button type="button" onClick={() => onCompareDevice(device.slug)}>Compare</button>
      </div>
    </article>
  );
}

export function RecommendationAssistant({ onOpenDevice, onCompareDevice }: Props) {
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
  const generationRef = useRef(0);

  function change<K extends keyof EditableFilters>(key: K, value: EditableFilters[K]) {
    setPending((current) => ({ ...current, [key]: value }));
  }

  function togglePriority(value: string) {
    const next = priorities.includes(value) ? priorities.filter((entry) => entry !== value) : [...priorities, value];
    setPriorities(next);
    // The backend does not accept an empty explicit priorities list. Reset the
    // conversation to clear historical priorities if no priorities remain.
    setPending((current) => {
      const updated = { ...current };
      if (next.length) updated.priorities = next;
      else delete updated.priorities;
      return updated;
    });
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
      const response = await converse(conversationPayload(sessionId, text, researchEnabled, explicit, guidanceEnabled), controller.signal);
      if (generation !== generationRef.current) return;
      setPending({});
      setMessages((current) => [...current, {
        id: response.query_id || uuid(), role: "assistant", text: response.explanation,
        results: response.results, needsResearch: response.needs_research,
        research: response.research, guidance: response.guidance, memoryUsed: response.memory_used,
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
        <div>
          <p className="eyebrow">Phone Discover · Pakistan</p>
          <h2 id="assistant-title">Your phone buying copilot.</h2>
          <p>Verified local database first. Opt into separate Gemini guidance or grounded web research; neither is a verified Pakistani market listing. Conversation memory stays in this tab.</p>
        </div>
        <button type="button" className="assistant-new-chat" onClick={() => void newChat()}>New chat + forget</button>
      </header>
      <div className="assistant-layout">
        <aside className="assistant-requirements">
          <div className="assistant-control">
            <span className="assistant-control-label">What matters most?</span>
            <div className="priority-grid">
              {PRIORITIES.map((value) => <button key={value} type="button" disabled={loading} className={priorities.includes(value) ? "active" : ""} aria-pressed={priorities.includes(value)} onClick={() => togglePriority(value)}>{value}</button>)}
            </div>
          </div>
          <div className="assistant-two-fields">
            <label className="assistant-field"><span>Maximum budget (PKR)</span>
              <div className="budget-input"><b>₨</b><input disabled={loading} type="number" min="1" max="999999999" value={budget} placeholder="80000" onChange={(event) => { const value = event.target.value; setBudget(value); if (value) change("budget_pkr", value); else setPending((current) => { const next = { ...current }; delete next.budget_pkr; return next; }); }} /></div>
            </label>
            <label className="assistant-field"><span>City</span><input disabled={loading} type="text" maxLength={100} value={city} placeholder="Lahore" onChange={(event) => { setCity(event.target.value); if (event.target.value.trim()) change("city", event.target.value.trim()); else setPending((current) => { const next = { ...current }; delete next.city; return next; }); }} /></label>
          </div>
          <div className="assistant-two-fields">
            <label className="assistant-field"><span>Condition</span><select disabled={loading} value={condition} onChange={(event) => { setCondition(event.target.value); if (event.target.value) change("condition", event.target.value); else setPending((current) => { const next = { ...current }; delete next.condition; return next; }); }}><option value="">From message / any</option><option value="box_pack">New / box pack</option><option value="open_box">Open box</option><option value="used">Used</option><option value="refurbished">Refurbished</option></select></label>
            <label className="assistant-field"><span>PTA status</span><select disabled={loading} value={ptaStatus} onChange={(event) => { setPtaStatus(event.target.value); if (event.target.value) change("pta_status", event.target.value); else setPending((current) => { const next = { ...current }; delete next.pta_status; return next; }); }}><option value="">From message / any</option><option value="approved">PTA approved (reported or checked)</option><option value="non_pta">Non-PTA</option><option value="cpid">CPID (not official approval)</option><option value="patched">Patched (not official approval)</option></select></label>
          </div>
          <label className="assistant-field"><span>PTA evidence requirement</span><select disabled={loading} value={ptaVerification} onChange={(event) => { setPtaVerification(event.target.value); if (event.target.value) change("pta_verification", event.target.value); else setPending((current) => { const next = { ...current }; delete next.pta_verification; return next; }); }}><option value="">Any available evidence</option><option value="reported">Seller/source reported</option><option value="checked">Independently checked evidence</option></select></label>
          <div className="assistant-two-fields">
            <label className="assistant-field"><span>Minimum RAM</span><select disabled={loading} value={ramMin} onChange={(event) => { setRamMin(event.target.value); if (event.target.value) change("ram_min", Number(event.target.value)); else setPending((current) => { const next = { ...current }; delete next.ram_min; return next; }); }}><option value="">Any</option><option value="6">6 GB</option><option value="8">8 GB</option><option value="12">12 GB</option><option value="16">16 GB</option></select></label>
            <label className="assistant-field"><span>Minimum storage</span><select disabled={loading} value={storageMin} onChange={(event) => { setStorageMin(event.target.value); if (event.target.value) change("storage_min", Number(event.target.value)); else setPending((current) => { const next = { ...current }; delete next.storage_min; return next; }); }}><option value="">Any</option><option value="128">128 GB</option><option value="256">256 GB</option><option value="512">512 GB</option></select></label>
          </div>
          <label className="strict-budget-toggle"><input type="checkbox" disabled={loading} checked={strictBudget} onChange={(event) => { setStrictBudget(event.target.checked); change("strict_budget", event.target.checked); }} /><span><strong>Strict PKR budget</strong><small>Require observed upper price bound to fit</small></span></label>
          <label className="strict-budget-toggle"><input type="checkbox" disabled={loading} checked={guidanceEnabled} onChange={(event) => setGuidanceEnabled(event.target.checked)} /><span><strong>Use Gemini general guidance</strong><small>Sends this message (with basic contact redaction) to Google if no eligible local matches. No web search, verified prices or PTA checks.</small></span></label>
          <label className="strict-budget-toggle"><input type="checkbox" disabled={loading} checked={researchEnabled} onChange={(event) => setResearchEnabled(event.target.checked)} /><span><strong>Request Gemini web research</strong><small>Separate Google Search grounding; requires API quota and opt-in. External sources are unverified.</small></span></label>
          <div className="quick-prompts"><span>Try asking</span>{QUICK_PROMPTS.map((prompt) => <button type="button" disabled={loading} key={prompt} onClick={() => setMessage(prompt)}>{prompt}</button>)}</div>
        </aside>
        <div className="assistant-conversation">
          <div className="chat-stream" aria-live="polite" aria-relevant="additions">
            {messages.map((entry) => <div className={`chat-message chat-${entry.role}`} key={entry.id}>
              <div className="chat-avatar">{entry.role === "assistant" ? "PD" : "You"}</div>
              <div className="chat-bubble">
                <p>{entry.text}</p>
                {entry.memoryUsed && <p className="pk-evidence-note">Preferences carried forward from this session.</p>}
                {entry.results && entry.results.length > 0 && <div className="pk-result-grid">{entry.results.map((result) => <PriceCard key={`${entry.id}-${result.device.slug}`} result={result} onOpenDevice={onOpenDevice} onCompareDevice={onCompareDevice} />)}</div>}
                {entry.needsResearch && <p className="pk-evidence-note">Local evidence is incomplete. You can opt in to web research; it will not create verified catalog entries.</p>}
                {entry.guidance?.status === "generated" && <div className="pk-research-preview pk-guidance-preview"><strong>Gemini general guidance · not verified</strong><p>{entry.guidance.notice}</p><p className="pk-research-summary">{entry.guidance.text}</p></div>}
                {entry.guidance && ["unavailable", "disabled", "rate_limited"].includes(entry.guidance.status) && <p className="pk-evidence-note" role="status">Gemini guidance: {entry.guidance.notice}</p>}
                {entry.research && entry.research.status !== "not_requested" && <div className="pk-research-preview"><strong>Gemini research: {entry.research.status.replaceAll("_", " ")}</strong><p>{entry.research.notice}</p>{entry.research.summary && <p className="pk-research-summary">{entry.research.summary}</p>}{entry.research.sources?.length > 0 && <ul>{entry.research.sources.map((source) => { const url = safeSourceUrl(source.url); return url ? <li key={url}><a href={url} target="_blank" rel="noopener noreferrer">{source.title || "Research source"} ↗</a></li> : null; })}</ul>}</div>}
              </div>
            </div>)}
            {loading && <div className="chat-message chat-assistant"><div className="chat-avatar">PD</div><div className="chat-bubble" role="status">Checking published devices and eligible price observations…</div></div>}
          </div>
          <form className="assistant-composer" onSubmit={(event) => void submit(event)}>
            <label htmlFor="pk-chat-message" className="pk-composer-label">Ask in English or Roman Urdu</label>
            <textarea id="pk-chat-message" maxLength={1000} disabled={loading} value={message} onChange={(event) => setMessage(event.target.value)} placeholder="80 hazar tak Lahore mein used PTA approved gaming phone batao…" rows={3} />
            <div><span role={error ? "alert" : undefined}>{error || "PKR observed asking prices only. Check PTA, condition and seller details yourself."}</span><button type="submit" disabled={loading || !message.trim()}>{loading ? "Finding matches…" : "Find local phones →"}</button></div>
          </form>
        </div>
      </div>
    </section>
  );
}
