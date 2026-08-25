import { useState } from "react";
import type { FormEvent } from "react";

type Result = {
  rank: number;
  recommended: boolean;
  score: number;
  match_percentage: number;
  device: {
    name: string;
    brand: string;
    slug: string;
    summary: string;
    status: string;
    primary_image_url: string;
  };
  variant: {
    name: string;
    ram_gb: number;
    storage_gb: number;
    battery_mah: number | null;
    display_refresh_hz: number | null;
    chipset: string;
    camera_score: number;
    gaming_score: number;
    battery_score: number;
  };
  strengths: string[];
  tradeoffs: string[];
  offer: {
    currency: string;
    price: string;
    seller_name: string;
    product_url: string;
    country_code: string;
    is_local: boolean;
  } | null;
  reason: string;
};

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  text: string;
  results?: Result[];
  source?: "deterministic" | "openai";
};

type Props = {
  onOpenDevice: (slug: string) => void;
  onCompareDevice: (slug: string) => void;
};

const PRIORITIES = [
  { value: "camera", label: "Camera", icon: "◉" },
  { value: "gaming", label: "Gaming", icon: "⌁" },
  { value: "battery", label: "Battery", icon: "ϟ" },
  { value: "display", label: "Display", icon: "▣" },
  { value: "value", label: "Value", icon: "◇" },
];

const QUICK_PROMPTS = [
  "Best camera phone under $500",
  "Gaming and battery phone under $700",
  "Best value phone with 12 GB RAM",
];

function makeId() {
  return typeof crypto !== "undefined" && crypto.randomUUID
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random()}`;
}

export function RecommendationAssistant({ onOpenDevice, onCompareDevice }: Props) {
  const [sessionId] = useState(makeId);
  const [message, setMessage] = useState("");
  const [budget, setBudget] = useState("");
  const [country, setCountry] = useState("US");
  const [currency, setCurrency] = useState("USD");
  const [priorities, setPriorities] = useState<string[]>([]);
  const [ramMin, setRamMin] = useState("");
  const [storageMin, setStorageMin] = useState("");
  const [strictBudget, setStrictBudget] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "welcome",
      role: "assistant",
      text: "Tell me your budget and what matters most. I’ll rank up to three catalog phones and explain the tradeoffs.",
    },
  ]);

  function togglePriority(priority: string) {
    setPriorities((current) =>
      current.includes(priority)
        ? current.filter((item) => item !== priority)
        : [...current, priority],
    );
  }

  function changeCountry(value: string) {
    const [countryCode, currencyCode] = value.split(":");
    setCountry(countryCode);
    setCurrency(currencyCode);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const requestText = message.trim() || `Find a phone focused on ${priorities.join(", ")}`;
    if (!message.trim() && !priorities.length && !budget && !ramMin && !storageMin) {
      setError("Describe your needs or select at least one requirement.");
      return;
    }

    setError("");
    setLoading(true);
    setMessages((current) => [...current, { id: makeId(), role: "user", text: requestText }]);
    setMessage("");

    try {
      const response = await fetch("/api/recommendations/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          message: requestText,
          budget: budget || null,
          country_code: country,
          currency,
          priorities,
          ram_min: Number(ramMin || 0),
          storage_min: Number(storageMin || 0),
          strict_budget: strictBudget,
        }),
      });
      const data = await response.json();
      if (!response.ok) {
        const detail = typeof data.detail === "string" ? data.detail : "Please check the requirements and try again.";
        throw new Error(detail);
      }
      setMessages((current) => [
        ...current,
        {
          id: data.query_id ?? makeId(),
          role: "assistant",
          text: data.explanation,
          results: data.results ?? [],
          source: data.response_source,
        },
      ]);
    } catch (requestError) {
      const errorMessage = requestError instanceof Error ? requestError.message : "Recommendation request failed.";
      setError(errorMessage);
      setMessages((current) => [
        ...current,
        { id: makeId(), role: "assistant", text: "I couldn’t complete that search. Check that the backend is running and try again." },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="assistant-card assistant-workspace" id="assistant">
      <header className="assistant-header">
        <div>
          <p className="eyebrow">Intelligent buying assistant</p>
          <h2>Turn requirements into a shortlist.</h2>
          <p>Catalog-grounded rankings first. Optional AI explanations when an API key is configured.</p>
        </div>
        <button
          type="button"
          className="assistant-new-chat"
          onClick={() => setMessages([{ id: "welcome-reset", role: "assistant", text: "Fresh start. What should your next phone be great at?" }])}
        >
          New chat
        </button>
      </header>

      <div className="assistant-layout">
        <aside className="assistant-requirements">
          <div className="assistant-control">
            <span className="assistant-control-label">Your priorities</span>
            <div className="priority-grid">
              {PRIORITIES.map((priority) => (
                <button
                  type="button"
                  className={priorities.includes(priority.value) ? "active" : ""}
                  onClick={() => togglePriority(priority.value)}
                  key={priority.value}
                >
                  <i>{priority.icon}</i>{priority.label}
                </button>
              ))}
            </div>
          </div>

          <div className="assistant-two-fields">
            <label className="assistant-field">
              <span>Maximum budget</span>
              <div className="budget-input"><b>{currency}</b><input type="number" min="0" value={budget} onChange={(event) => setBudget(event.target.value)} placeholder="500" /></div>
            </label>
            <label className="assistant-field">
              <span>Market</span>
              <select value={`${country}:${currency}`} onChange={(event) => changeCountry(event.target.value)}>
                <option value="US:USD">United States</option>
                <option value="PK:PKR">Pakistan</option>
                <option value="GB:GBP">United Kingdom</option>
                <option value="AE:AED">United Arab Emirates</option>
                <option value="IN:INR">India</option>
              </select>
            </label>
          </div>

          <div className="assistant-two-fields">
            <label className="assistant-field">
              <span>Minimum RAM</span>
              <select value={ramMin} onChange={(event) => setRamMin(event.target.value)}>
                <option value="">Any</option><option value="8">8 GB</option><option value="12">12 GB</option><option value="16">16 GB</option>
              </select>
            </label>
            <label className="assistant-field">
              <span>Minimum storage</span>
              <select value={storageMin} onChange={(event) => setStorageMin(event.target.value)}>
                <option value="">Any</option><option value="128">128 GB</option><option value="256">256 GB</option><option value="512">512 GB</option>
              </select>
            </label>
          </div>

          <label className="strict-budget-toggle">
            <input type="checkbox" checked={strictBudget} onChange={(event) => setStrictBudget(event.target.checked)} />
            <span><strong>Strict budget</strong><small>Hide phones above the limit</small></span>
          </label>

          <div className="quick-prompts">
            <span>Quick ideas</span>
            {QUICK_PROMPTS.map((prompt) => <button type="button" onClick={() => setMessage(prompt)} key={prompt}>{prompt}</button>)}
          </div>
        </aside>

        <div className="assistant-conversation">
          <div className="chat-stream" aria-live="polite">
            {messages.map((chatMessage) => (
              <div className={`chat-message chat-${chatMessage.role}`} key={chatMessage.id}>
                <div className="chat-avatar">{chatMessage.role === "assistant" ? "MD" : "You"}</div>
                <div className="chat-bubble">
                  <p>{chatMessage.text}</p>
                  {chatMessage.source && <span className="response-source">{chatMessage.source === "openai" ? "AI explanation" : "Catalog engine"}</span>}
                  {chatMessage.results && (
                    <div className="assistant-results-grid">
                      {chatMessage.results.map((result) => (
                        <article className={`assistant-result-card ${result.recommended ? "assistant-result-best" : ""}`} key={result.device.slug}>
                          {result.recommended && <span className="assistant-best-label">Best match</span>}
                          <div className="assistant-result-top">
                            <div className="assistant-result-image">
                              {result.device.primary_image_url ? <img src={result.device.primary_image_url} alt="" /> : <span>{result.device.brand[0]}</span>}
                            </div>
                            <div><small>{result.device.brand}</small><h3>{result.device.name}</h3><span>{result.variant.name}</span></div>
                            <div className="match-score"><strong>{result.match_percentage}%</strong><span>match</span></div>
                          </div>
                          <div className="assistant-strengths">
                            {result.strengths.map((strength) => <span key={strength}>{strength}</span>)}
                          </div>
                          {result.tradeoffs.length > 0 && <p className="assistant-tradeoff">Consider: {result.tradeoffs.join(" · ")}</p>}
                          <div className="assistant-result-footer">
                            <div>{result.offer ? <><small>{result.offer.seller_name}</small><strong>{result.offer.currency} {result.offer.price}</strong></> : <strong>Price unavailable</strong>}</div>
                            <div className="assistant-result-actions">
                              <button type="button" onClick={() => onCompareDevice(result.device.slug)}>Compare</button>
                              <button type="button" onClick={() => onOpenDevice(result.device.slug)}>View phone</button>
                              {result.offer && <a href={result.offer.product_url} target="_blank" rel="noreferrer">Visit seller ↗</a>}
                            </div>
                          </div>
                        </article>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}
            {loading && <div className="chat-message chat-assistant"><div className="chat-avatar">MD</div><div className="chat-bubble chat-thinking"><i /><i /><i /></div></div>}
          </div>

          <form className="assistant-composer" onSubmit={submit}>
            <textarea value={message} onChange={(event) => setMessage(event.target.value)} placeholder="Example: I need the best camera and battery phone under $600…" rows={3} />
            <div>
              <span>{error || "Recommendations use verified catalog data and active offers."}</span>
              <button type="submit" disabled={loading}>{loading ? "Finding matches…" : "Get recommendations →"}</button>
            </div>
          </form>
        </div>
      </div>
    </section>
  );
}
