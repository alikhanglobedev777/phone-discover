import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import type { Brand } from "../types";
import {
  buildFinderRequest, formatPriceRange, recommendLocalPhones, safeSourceUrl,
} from "../lib/pakistan";
import type { FinderInput, LocalRecommendationResponse } from "../lib/pakistan";
import "../phone-finder.css";

type Props = {
  brands: Brand[];
  onOpenDevice: (slug: string) => void;
  onCompareDevice: (slug: string) => void;
};

type SavedPhone = { slug: string; name: string };
type SavedSearch = { id: string; label: string; filters: FinderInput };
const SEARCHES_KEY = "phone-discover-finder-searches-v1";
const PHONES_KEY = "phone-discover-saved-phones-v1";
const OPTIONS = [
  { value: "camera", title: "Camera", text: "Photography and video" },
  { value: "gaming", title: "Gaming", text: "Performance and smooth play" },
  { value: "battery", title: "Battery", text: "Lasting longer each day" },
  { value: "display", title: "Display", text: "Visual smoothness" },
  { value: "value", title: "Value", text: "Price within your budget" },
] as const;

const defaults: FinderInput = {
  budget_pkr: "", city: "", condition: "", pta_status: "",
  pta_verification: "", brand: "", priorities: [], ram_min: "",
  storage_min: "", strict_budget: true,
};

function readSavedPhones(): SavedPhone[] {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(PHONES_KEY) ?? "[]");
    if (!Array.isArray(value)) return [];
    return value.filter((x): x is SavedPhone =>
      x !== null && typeof x === "object" &&
      typeof x.slug === "string" && x.slug.length <= 220 &&
      typeof x.name === "string" && x.name.length <= 240).slice(0, 30);
  } catch { return []; }
}

function readSavedSearches(): SavedSearch[] {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(SEARCHES_KEY) ?? "[]");
    if (!Array.isArray(value)) return [];
    return value.filter((x): x is SavedSearch =>
      x !== null && typeof x === "object" &&
      typeof x.id === "string" && typeof x.label === "string" &&
      x.filters !== null && typeof x.filters === "object" &&
      Array.isArray(x.filters.priorities)).slice(0, 8);
  } catch { return []; }
}

function shortLabel(filters: FinderInput) {
  const amount = Number(filters.budget_pkr);
  const price = Number.isFinite(amount) && amount > 0
    ? `Under PKR ${amount.toLocaleString("en-PK")}` : "Any budget";
  return [price, filters.city.trim(), filters.condition.replaceAll("_", " "),
    filters.priorities.join(" + ")].filter(Boolean).join(" · ").slice(0, 140);
}

export function PhoneFinder({ brands, onOpenDevice, onCompareDevice }: Props) {
  const [filters, setFilters] = useState<FinderInput>({ ...defaults });
  const [step, setStep] = useState<0 | 1 | 2>(0);
  const [results, setResults] = useState<LocalRecommendationResponse | null>(null);
  const [savedPhones, setSavedPhones] = useState(readSavedPhones);
  const [savedSearches, setSavedSearches] = useState(readSavedSearches);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);

  function update<K extends keyof FinderInput>(key: K, value: FinderInput[K]) {
    setFilters((current) => ({ ...current, [key]: value }));
  }

  function togglePriority(priority: string) {
    update("priorities", filters.priorities.includes(priority)
      ? filters.priorities.filter((value) => value !== priority)
      : [...filters.priorities, priority]);
  }

  function toggleSavedPhone(phone: SavedPhone) {
    const next = savedPhones.some((item) => item.slug === phone.slug)
      ? savedPhones.filter((item) => item.slug !== phone.slug)
      : [phone, ...savedPhones].slice(0, 30);
    setSavedPhones(next);
    try { localStorage.setItem(PHONES_KEY, JSON.stringify(next)); } catch { /* Guest storage optional */ }
  }

  function saveSearch() {
    const entry: SavedSearch = {
      id: String(Date.now()) + "-" + Math.random().toString(36).slice(2, 8),
      label: shortLabel(filters), filters: { ...filters, priorities: [...filters.priorities] },
    };
    const next = [entry, ...savedSearches].slice(0, 8);
    setSavedSearches(next);
    try { localStorage.setItem(SEARCHES_KEY, JSON.stringify(next)); } catch { /* Guest storage optional */ }
  }

  function removeSearch(id: string) {
    const next = savedSearches.filter((entry) => entry.id !== id);
    setSavedSearches(next);
    try { localStorage.setItem(SEARCHES_KEY, JSON.stringify(next)); } catch { /* Guest storage optional */ }
  }

  async function search(event?: FormEvent) {
    event?.preventDefault();
    if (loading) return;
    controller.current?.abort();
    const abort = new AbortController();
    controller.current = abort;
    setLoading(true); setError(""); setResults(null);
    try {
      const data = await recommendLocalPhones(buildFinderRequest(filters), abort.signal);
      if (!abort.signal.aborted) { setResults(data); setStep(2); }
    } catch (reason) {
      if (!abort.signal.aborted) setError(reason instanceof Error ? reason.message : "Could not find recommendations.");
    } finally {
      if (!abort.signal.aborted) setLoading(false);
    }
  }

  const empty = results?.results.length === 0;
  return (
    <section className="finder-section" id="finder" aria-labelledby="finder-title">
      <div className="finder-heading">
        <p className="eyebrow">Personalized phone discovery</p>
        <h2 id="finder-title">Find the phone that fits your life.</h2>
        <p>Tell us what matters. We match your requirements against actual catalog variants and source-backed Pakistan price observations, without inventing prices or PTA approval.</p>
      </div>
      <div className="finder-surface">
        <div className="finder-steps" aria-label="Phone finder progress">
          {["Your budget", "Your priorities", "Your matches"].map((name, index) => (
            <span key={name} className={step === index ? "active" : step > index ? "done" : ""}>
              <b>{index + 1}</b> {name}
            </span>
          ))}
        </div>
        {step === 0 && (
          <div className="finder-form">
            <h3>What are you shopping for?</h3>
            <div className="finder-fields">
              <label>Maximum budget (PKR)
                <input value={filters.budget_pkr} type="number" min="1" max="999999999" placeholder="100000"
                  onChange={(event) => update("budget_pkr", event.target.value)} />
              </label>
              <label>City (optional)
                <input value={filters.city} maxLength={100} placeholder="Lahore"
                  onChange={(event) => update("city", event.target.value)} />
              </label>
              <label>Condition
                <select value={filters.condition} onChange={(event) => update("condition", event.target.value)}>
                  <option value="">Any condition</option>
                  <option value="box_pack">New / box pack</option>
                  <option value="open_box">Open box</option>
                  <option value="used">Used</option>
                  <option value="refurbished">Refurbished</option>
                </select>
              </label>
              <label>PTA status
                <select value={filters.pta_status} onChange={(event) => {
                  const value = event.target.value;
                  update("pta_status", value);
                  if (value !== "approved") update("pta_verification", "");
                }}>
                  <option value="">Any PTA status</option>
                  <option value="approved">PTA approved (reported or checked)</option>
                  <option value="non_pta">Non-PTA</option>
                  <option value="cpid">CPID (not official approval)</option>
                  <option value="patched">Patched (not official approval)</option>
                </select>
              </label>
              <label>PTA evidence requirement
                <select value={filters.pta_verification} disabled={filters.pta_status !== "approved"}
                  onChange={(event) => update("pta_verification", event.target.value)}>
                  <option value="">Seller-reported or checked</option>
                  <option value="checked">Independently checked only</option>
                </select>
              </label>
              <label>Preferred brand
                <select value={filters.brand} onChange={(event) => update("brand", event.target.value)}>
                  <option value="">Any brand</option>
                  {brands.map((brand) => <option key={brand.slug} value={brand.slug}>{brand.name}</option>)}
                </select>
              </label>
            </div>
            <p className="finder-help">Leave fields blank to search broadly. An observed price is not live stock, and PTA status must be verified for the exact handset.</p>
            <div className="finder-actions"><button type="button" onClick={() => setStep(1)}>Continue →</button></div>
          </div>
        )}
        {step === 1 && (
          <form className="finder-form" onSubmit={(event) => void search(event)}>
            <h3>What matters most?</h3>
            <p>Select one or more priorities, or leave them empty for a balanced shortlist. Ratings are editorial signals, not certified benchmarks.</p>
            <div className="finder-priorities">
              {OPTIONS.map((option) => (
                <label key={option.value} className={filters.priorities.includes(option.value) ? "selected" : ""}>
                  <input type="checkbox" checked={filters.priorities.includes(option.value)}
                    onChange={() => togglePriority(option.value)} />
                  <strong>{option.title}</strong><small>{option.text}</small>
                </label>
              ))}
            </div>
            <div className="finder-fields">
              <label>Minimum RAM
                <select value={filters.ram_min} onChange={(event) => update("ram_min", event.target.value)}>
                  <option value="">Any</option>
                  {[4, 6, 8, 12, 16].map((value) => <option key={value} value={value}>{value} GB</option>)}
                </select>
              </label>
              <label>Minimum storage
                <select value={filters.storage_min} onChange={(event) => update("storage_min", event.target.value)}>
                  <option value="">Any</option>
                  {[64, 128, 256, 512, 1024].map((value) => <option key={value} value={value}>{value} GB</option>)}
                </select>
              </label>
            </div>
            <label className="finder-toggle"><input type="checkbox" checked={filters.strict_budget}
              onChange={(event) => update("strict_budget", event.target.checked)} />
              Require the entire observed asking-price range to fit my budget
            </label>
            <div className="finder-actions">
              <button type="button" className="secondary" onClick={() => setStep(0)}>← Back</button>
              <button type="submit" disabled={loading}>{loading ? "Checking catalog…" : "Find my phones →"}</button>
            </div>
            {error && <p className="finder-error" role="alert">{error}</p>}
          </form>
        )}
        {step === 2 && results && (
          <div className="finder-results">
            <div className="finder-results-heading">
              <div><h3>Your phone shortlist</h3><p>{results.explanation}</p></div>
              <div className="finder-actions">
                <button type="button" className="secondary" onClick={() => { setStep(0); setResults(null); }}>Edit preferences</button>
                <button type="button" onClick={saveSearch}>Save this search</button>
              </div>
            </div>
            {results.coverage_incomplete && <p className="finder-warning" role="status">Only part of the catalog could be assessed. Treat this as a shortlist, not a market-wide ranking.</p>}
            {empty && <div className="finder-empty" role="status">
              <strong>No exact evidence-backed matches yet.</strong>
              <p>Try a higher budget, a different condition or city, or relax the PTA evidence requirement. Missing results do not prove that a phone is unavailable.</p>
              <button type="button" onClick={() => { setStep(0); setResults(null); }}>Adjust my filters</button>
              <a href="#market">Browse observed Pakistan market prices</a>
            </div>}
            <div className="finder-result-grid">
              {results.results.map((result) => {
                const price = result.market_price;
                const source = safeSourceUrl(price.source_url);
                const phone = { slug: result.device.slug, name: `${result.device.brand} ${result.device.name}` };
                const isSaved = savedPhones.some((item) => item.slug === phone.slug);
                return <article className="finder-card" key={`${phone.slug}-${result.variant.id}`}>
                  <div className="finder-card-top">
                    {result.device.primary_image_url
                      ? <img src={result.device.primary_image_url} alt="" loading="lazy" />
                      : <span className="finder-photo-pending" aria-hidden="true">PD</span>}
                    <div><small>Match #{result.rank}{result.recommended ? " · Best documented match" : ""}</small>
                      <h4>{phone.name}</h4>
                      <p>{result.variant.ram_gb} GB RAM · {result.variant.storage_gb} GB storage</p></div>
                  </div>
                  <strong className="finder-price">{formatPriceRange(price)}</strong>
                  <p className="finder-meta">{price.condition.replaceAll("_", " ")} · {price.city || "Pakistan"} · {price.pta_status.replaceAll("_", " ")} ({price.pta_verification === "checked" ? "checked" : "reported / unconfirmed"})</p>
                  {result.fit_score !== null && <p className="finder-score">Catalog fit: {result.fit_score.toFixed(0)}/100 <small>editorial heuristic</small></p>}
                  {result.fit_score === null && <p className="finder-warning">No comparable quality score; not a verified best-phone claim.</p>}
                  <div className="finder-evidence">
                    <strong>Why it may fit</strong>
                    {result.strengths.map((value) => <p key={value}>+ {value}</p>)}
                    <strong>What to consider</strong>
                    {result.tradeoffs.map((value) => <p key={value}>• {value}</p>)}
                    <p>Observed {new Date(price.observed_at).toLocaleDateString("en-PK")} · availability not guaranteed</p>
                    {source && <a href={source} target="_blank" rel="noopener noreferrer">View evidence source ↗</a>}
                  </div>
                  <div className="finder-card-actions">
                    <button type="button" onClick={() => onOpenDevice(phone.slug)}>Details</button>
                    <button type="button" onClick={() => onCompareDevice(phone.slug)}>+ Compare</button>
                    <button type="button" aria-pressed={isSaved} onClick={() => toggleSavedPhone(phone)}>
                      {isSaved ? "♥ Saved" : "♡ Save"}
                    </button>
                  </div>
                </article>;
              })}
            </div>
            {results.needs_research && !empty && <p className="finder-help">Evidence is limited for some matches. This tool does not automatically run paid web research; use the AI assistant to request an explicit source-backed check.</p>}
            <p className="finder-help">Prices are observed asking ranges, not quotes or live inventory. Score gaps and seller-reported PTA claims are shown explicitly.</p>
          </div>
        )}
        <div className="finder-saved">
          <h3>Your saved phones and searches <small>Saved only in this browser</small></h3>
          {!savedPhones.length && !savedSearches.length && <p>Save a recommended phone or search to revisit it later without creating an account.</p>}
          {!!savedPhones.length && <div className="finder-saved-items">
            {savedPhones.map((phone) => <div key={phone.slug} className="finder-saved-item">
              <button type="button" onClick={() => onOpenDevice(phone.slug)}>{phone.name}</button>
              <button type="button" aria-label={`Remove ${phone.name} from saved phones`} onClick={() => toggleSavedPhone(phone)}>×</button>
            </div>)}
          </div>}
          {!!savedSearches.length && <div className="finder-saved-items">
            {savedSearches.map((search) => <div key={search.id} className="finder-saved-item">
              <button type="button" onClick={() => { controller.current?.abort(); setLoading(false); setFilters({ ...search.filters, priorities: [...search.filters.priorities] }); setResults(null); setStep(0); }}>{search.label}</button>
              <button type="button" aria-label={`Delete saved search ${search.label}`} onClick={() => removeSearch(search.id)}>×</button>
            </div>)}
          </div>}
        </div>
      </div>
    </section>
  );
}
