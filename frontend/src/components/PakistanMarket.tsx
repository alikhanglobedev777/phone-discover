import { useState } from "react";
import type { FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { formatPriceRange, marketQuery, safeSourceUrl, searchPakistaniMarket } from "../lib/pakistan";
import type { MarketSearchFilters, MarketSearchResult } from "../lib/pakistan";

const DEFAULTS: MarketSearchFilters = {
  q: "", city: "", condition: "", pta_status: "", pta_verification: "",
  budget_pkr: "", ram_min: "", sort: "price",
};

type Props = { onOpenDevice: (slug: string) => void; onCompareDevice: (slug: string) => void };

function MarketCard({ result, onOpenDevice, onCompareDevice }: Props & { result: MarketSearchResult }) {
  const price = result.price_observation;
  const source = safeSourceUrl(price.source_url);
  return (
    <article className="pk-market-card">
      <div className="pk-market-card-main">
        {result.primary_image_url ? <img src={result.primary_image_url} alt="" loading="lazy" /> : <span className="pk-phone-placeholder" aria-hidden="true">▣</span>}
        <div>
          <p className="pk-kicker">{result.brand.name} · {result.variant.ram_gb} / {result.variant.storage_gb} GB</p>
          <h3>{result.name}</h3>
          <strong className="pk-market-asking">{formatPriceRange(price)}</strong>
          <p className="pk-market-meta">{price.condition.replaceAll("_", " ")}{price.grade ? ` · ${price.grade}` : ""} · {price.city || "Pakistan"}</p>
        </div>
      </div>
      <div className="pk-market-evidence">
        {price.evidence_type === "web_researched" && <p><strong>Web researched:</strong> saved source-reported price; independent review pending.</p>}
        <p><strong>PTA:</strong> {price.pta_status.replaceAll("_", " ")} · {price.pta_verification === "checked" ? "independently checked evidence" : "reported / unconfirmed"}</p>
        <p><strong>Price observed:</strong> {new Date(price.observed_at).toLocaleDateString("en-PK")} · availability not confirmed</p>
        {source && <p><a href={source} rel="noopener noreferrer" target="_blank">View evidence source ↗</a></p>}
      </div>
      <div className="pk-market-card-actions">
        <button type="button" onClick={() => onOpenDevice(result.slug)} aria-label={`View details for ${result.name}`}>View details</button>
        <button type="button" onClick={() => onCompareDevice(result.slug)} aria-label={`Add ${result.name} to comparison`}>+ Compare</button>
      </div>
    </article>
  );
}

export function PakistanMarket({ onOpenDevice, onCompareDevice }: Props) {
  const [draft, setDraft] = useState<MarketSearchFilters>(DEFAULTS);
  const [filters, setFilters] = useState<MarketSearchFilters>(DEFAULTS);
  const [page, setPage] = useState(1);
  const queryString = marketQuery(filters, page);
  const query = useQuery({
    queryKey: ["pakistan-market", queryString],
    queryFn: () => searchPakistaniMarket(filters, page),
    staleTime: 30_000,
  });

  function update(key: keyof MarketSearchFilters, value: string) {
    setDraft((current) => ({ ...current, [key]: value }));
  }

  function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setFilters({ ...draft }); setPage(1);
  }

  function clear() {
    setDraft({ ...DEFAULTS }); setFilters({ ...DEFAULTS }); setPage(1);
  }

  return (
    <section className="pk-market-section" id="market" aria-labelledby="pk-market-title">
      <div className="pk-market-heading">
        <div><p className="eyebrow">Discover / Pakistan market</p><h2 id="pk-market-title">Understand the price before you buy.</h2>
          <p>Explore Pakistani asking-price observations by model, budget, PTA status and condition. Each result shows its source and observation date.</p>
        </div>
      </div>
      <form className="pk-market-filter" onSubmit={search}>
        <label><span>Phone or chipset</span><input value={draft.q} maxLength={120} placeholder="Samsung, Redmi, Snapdragon…" onChange={(event) => update("q", event.target.value)} /></label>
        <label><span>City</span><input value={draft.city} maxLength={100} placeholder="Lahore" onChange={(event) => update("city", event.target.value)} /></label>
        <label><span>Budget (PKR)</span><input value={draft.budget_pkr} type="number" min="1" max="999999999" placeholder="80000" onChange={(event) => update("budget_pkr", event.target.value)} /></label>
        <label><span>Condition</span><select value={draft.condition} onChange={(event) => update("condition", event.target.value)}><option value="">Any</option><option value="box_pack">New / box pack</option><option value="open_box">Open box</option><option value="used">Used</option><option value="refurbished">Refurbished</option></select></label>
        <label><span>PTA status</span><select value={draft.pta_status} onChange={(event) => update("pta_status", event.target.value)}><option value="">Any</option><option value="approved">Approved (reported or checked)</option><option value="non_pta">Non-PTA</option><option value="cpid">CPID</option><option value="patched">Patched</option></select></label>
        <label><span>PTA evidence</span><select value={draft.pta_verification} onChange={(event) => update("pta_verification", event.target.value)}><option value="">Any</option><option value="reported">Source reported</option><option value="checked">Independently checked</option></select></label>
        <label><span>Minimum RAM</span><select value={draft.ram_min} onChange={(event) => update("ram_min", event.target.value)}><option value="">Any</option><option value="6">6 GB</option><option value="8">8 GB</option><option value="12">12 GB</option><option value="16">16 GB</option></select></label>
        <label><span>Sort</span><select value={draft.sort} onChange={(event) => update("sort", event.target.value)}><option value="price">Lowest observed price</option><option value="relevance">Relevance</option><option value="camera">Camera catalog score</option><option value="gaming">Gaming catalog score</option><option value="battery">Battery catalog score</option><option value="newest">Newest model</option></select></label>
        <div className="pk-market-filter-actions"><button type="submit">Search market</button><button type="button" className="pk-market-clear" onClick={clear}>Clear filters</button></div>
      </form>
      {query.isLoading && <p className="state-message" role="status">Loading price-backed Pakistani phones…</p>}
      {query.isError && <div className="state-message error" role="alert"><p>We couldn't load price observations right now.</p><button className="retry-button" type="button" onClick={() => void query.refetch()}>Try again</button></div>}
      {query.data && <>
        <div className="pk-market-summary"><span>{query.data.count} price-backed phones found</span><span>Page {query.data.page}</span></div>
        {query.data.results.length === 0 && <div className="empty-state"><strong>{query.data.catalog_status === "empty" ? "The phone catalog is empty" : "No eligible local price evidence"}</strong><p>{query.data.catalog_status === "empty" ? "Phones and Pakistani prices need to be imported before this search can return results." : query.data.catalog_status === "missing_prices" ? "Catalog phones need eligible Pakistani price observations before they can appear here." : "Try another condition, city, budget, or PTA requirement. These filters do not match the available evidence."}</p>{query.data.catalog_status === "ready" && <button type="button" onClick={clear}>Reset search</button>}</div>}
        <div className="pk-market-grid">{query.data.results.map((result) => <MarketCard key={`${result.slug}-${result.variant.id}`} result={result} onOpenDevice={onOpenDevice} onCompareDevice={onCompareDevice} />)}</div>
        <p className="pk-market-disclaimer">{query.data.price_disclaimer || "Observed asking prices are not live offers, and handset/PTA status requires independent verification."}</p>
        {(page > 1 || query.data.has_more) && <div className="pk-pagination"><button type="button" disabled={page <= 1 || query.isFetching} onClick={() => setPage((current) => Math.max(1, current - 1))}>← Previous</button><span>Page {page}</span><button type="button" disabled={!query.data.has_more || query.isFetching} onClick={() => setPage((current) => current + 1)}>Next →</button></div>}
      </>}
    </section>
  );
}
