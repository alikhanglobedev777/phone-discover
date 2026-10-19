import { useDeferredValue, useEffect, useMemo, useState } from "react";
import { useInfiniteQuery, useQueries, useQuery } from "@tanstack/react-query";
import { getBrands, getDevice, getDevices } from "./lib/api";
import { CatalogFilters } from "./components/CatalogFilters";
import { ComparisonModal } from "./components/ComparisonModal";
import { ComparisonTray } from "./components/ComparisonTray";
import { PhoneCard } from "./components/PhoneCard";
import { PakistanMarket } from "./components/PakistanMarket";
import { PhoneDetail } from "./components/PhoneDetail";
import { AssistantDrawer } from "./components/AssistantDrawer";
import type { Device, DeviceFilters } from "./types";
import type { MarketSearchFilters } from "./lib/pakistan";

const EMPTY_FILTERS: DeviceFilters = {
  search: "",
  brand: "",
  status: "",
  price_max: "",
  ram_min: "",
  storage_min: "",
  camera_score_min: "",
  gaming_score_min: "",
  country: "",
};

const COMPARISON_STORAGE_KEY = "mobile-discovery-comparison";

function initialComparisonSlugs() {
  const fromUrl = new URLSearchParams(window.location.search)
    .get("compare")
    ?.split(",")
    .map((slug) => slug.trim())
    .filter(Boolean);
  if (fromUrl?.length) return [...new Set(fromUrl)].slice(0, 3);

  try {
    const stored = JSON.parse(localStorage.getItem(COMPARISON_STORAGE_KEY) ?? "[]");
    if (Array.isArray(stored)) {
      return [...new Set(stored.filter((slug): slug is string => typeof slug === "string"))].slice(0, 3);
    }
  } catch {
    // Storage may be blocked entirely (e.g. restrictive browser settings).
    try { localStorage.removeItem(COMPARISON_STORAGE_KEY); } catch { /* Non-persistent shortlist still works. */ }
  }
  return [];
}

export default function App() {
  const [filters, setFilters] = useState<DeviceFilters>(EMPTY_FILTERS);
  const [activeSlug, setActiveSlug] = useState<string | null>(() => new URLSearchParams(window.location.search).get("device"));
  const [compareSlugs, setCompareSlugs] = useState<string[]>(initialComparisonSlugs);
  const [comparisonNotice, setComparisonNotice] = useState("");
  const [marketResearchRequest, setMarketResearchRequest] = useState<{ id: number; filters: MarketSearchFilters } | null>(null);
  const [showComparison, setShowComparison] = useState(
    () => (new URLSearchParams(window.location.search).get("compare")?.split(",").filter(Boolean).length ?? 0) >= 2,
  );
  const deferredSearch = useDeferredValue(filters.search);
  const queryFilters = useMemo(
    () => ({ ...filters, search: deferredSearch }),
    [deferredSearch, filters],
  );
  const devicesQuery = useInfiniteQuery({
    queryKey: ["devices", queryFilters],
    queryFn: ({ pageParam }) => getDevices(queryFilters, pageParam),
    initialPageParam: 1,
    getNextPageParam: (lastPage, allPages) => lastPage.next ? allPages.length + 1 : undefined,
  });
  const brandsQuery = useQuery({ queryKey: ["brands"], queryFn: getBrands });
  const activeQuery = useQuery({
    queryKey: ["device", activeSlug],
    queryFn: () => getDevice(activeSlug!),
    enabled: Boolean(activeSlug),
  });
  const comparisonQueries = useQueries({
    queries: compareSlugs.map((slug) => ({
      queryKey: ["device", slug],
      queryFn: () => getDevice(slug),
      staleTime: 60_000,
    })),
  });
  const devices = devicesQuery.data?.pages.flatMap((page) => page.results) ?? [];
  const deviceCount = devicesQuery.data?.pages[0]?.count ?? 0;
  const compareDevices = comparisonQueries.flatMap((query) => query.data ? [query.data] : []);
  const comparisonLoading = comparisonQueries.some((query) => query.isLoading);

  useEffect(() => {
    try {
      localStorage.setItem(COMPARISON_STORAGE_KEY, JSON.stringify(compareSlugs));
    } catch {
      // The URL still preserves the shortlist when storage is unavailable.
    }
    const url = new URL(window.location.href);
    if (compareSlugs.length) url.searchParams.set("compare", compareSlugs.join(","));
    else url.searchParams.delete("compare");
    if (activeSlug) url.searchParams.set("device", activeSlug);
    else url.searchParams.delete("device");
    window.history.replaceState({}, "", url);
  }, [activeSlug, compareSlugs]);

  useEffect(() => {
    if (compareSlugs.length < 2) setShowComparison(false);
  }, [compareSlugs.length]);

  function toggleCompare(device: Device) {
    if (compareSlugs.includes(device.slug)) {
      setCompareSlugs((current) => current.filter((slug) => slug !== device.slug));
      setComparisonNotice("");
    } else if (compareSlugs.length >= 3) {
      setComparisonNotice("Your comparison is full. Remove a phone to add another.");
    } else {
      setCompareSlugs((current) => [...current, device.slug]);
      setComparisonNotice("");
    }
  }

  function removeComparison(slug: string) {
    setCompareSlugs((current) => current.filter((item) => item !== slug));
    setComparisonNotice("");
  }

  function addComparison(slug: string) {
    if (compareSlugs.includes(slug)) {
      setComparisonNotice("This phone is already in your shortlist.");
    } else if (compareSlugs.length >= 3) {
      setComparisonNotice("Your comparison is full. Remove a phone to add another.");
    } else {
      setCompareSlugs((current) => [...current, slug]);
      setComparisonNotice("");
    }
  }

  return (
    <main className={`shell ${compareSlugs.length ? "compare-active" : ""}`} id="main-content">
      <a className="skip-link" href="#catalog">Skip to phone catalog</a>
      <nav className="nav" aria-label="Main navigation">
        <a className="brand-mark" href="#top" aria-label="Phone Discover home"><span className="brand-symbol" aria-hidden="true">P.</span><span>phone<span className="brand-light">discover</span><small>FIND YOUR NEXT PHONE</small></span></a>
        <div className="nav-actions">
          <a className="nav-link" href="#catalog">Explore phones</a>
          <a className="nav-link" href="#market">Pakistan prices</a>
          <a className="nav-link" href="#how-it-works">How it works</a>
        </div>
      </nav>
      <section className="hero" id="top" aria-labelledby="hero-title">
        <div className="hero-content">
          <p className="eyebrow"><span className="eyebrow-line" aria-hidden="true"/> A smarter way to choose</p>
          <h1 id="hero-title">Find a phone worth<br/><span>falling for.</span></h1>
          <p className="hero-copy">Discover the phones that fit your life. Explore the full catalog, compare the details, and check Pakistan market price evidence before you decide.</p>
          <div className="hero-actions">
            <a className="hero-cta" href="#catalog">Explore all phones <span aria-hidden="true">↗</span></a>
            <a className="hero-secondary" href="#market">Browse PKR prices <span aria-hidden="true">→</span></a>
          </div>
          <p className="hero-smallprint">Explore freely · Compare up to three phones · Price evidence clearly labeled</p>
        </div>
        <div className="hero-visual" aria-label="How Phone Discover helps you decide">
          <div className="hero-visual-top"><span className="visual-kicker">THE BETTER WAY TO BUY</span><span className="visual-plus" aria-hidden="true">↗</span></div>
          <div className="hero-visual-body">
            <span className="visual-number">01 / 03</span>
            <span className="visual-large">Good phones.<br/>Better decisions.</span>
            <p>The whole catalog is yours to explore. Open the assistant on the right whenever you want a second opinion.</p>
          </div>
          <div className="hero-visual-bottom"><span>Explore</span><span>Compare</span><span>Choose</span></div>
        </div>
      </section>
      <section className="catalog-section" id="catalog" aria-labelledby="catalog-heading">
        <div className="section-heading">
          <div>
            <p className="eyebrow">The phone edit / every model</p>
            <h2 id="catalog-heading">{Object.values(filters).some(Boolean) ? "Your matching phones" : "Explore every phone."}</h2>
            <p className="catalog-heading-copy">Browse the collection, shortlist your favourites and compare what matters. Load more to explore the complete catalog.</p>
          </div>
          <span className="catalog-counter">{deviceCount.toLocaleString("en-PK")} phones in catalog</span>
        </div>
        {brandsQuery.isError && <div className="brand-filter-error" role="status">Brand options aren't available right now. <button type="button" className="retry-button" onClick={() => void brandsQuery.refetch()}>Retry brands</button></div>}
        <CatalogFilters
          brands={brandsQuery.data?.results ?? []}
          filters={filters}
          onChange={setFilters}
          onReset={() => setFilters(EMPTY_FILTERS)}
        />
        <p className="pk-market-disclaimer">Catalog offers may be in different currencies and are not directly comparable. For evidence-backed Pakistan prices, use the PKR market search below.</p>
        {devicesQuery.isLoading && <p className="state-message">Loading phones…</p>}
        {devicesQuery.isError && !devicesQuery.data && <div className="state-message error" role="alert"><p>We couldn't load the catalog right now.</p><button type="button" className="retry-button" onClick={() => void devicesQuery.refetch()}>Try again</button></div>}
        {!devicesQuery.isLoading && !devicesQuery.isError && !devices.length && (
          <div className="empty-state">
            <strong>No matching phones</strong>
            <p>Try clearing one or more filters, or add more devices from the admin panel.</p>
            <button type="button" onClick={() => setFilters(EMPTY_FILTERS)}>Clear all filters</button>
          </div>
        )}
        <div className="phone-grid" aria-busy={devicesQuery.isFetching && !devicesQuery.isFetchingNextPage}>
          {devices.map((device) => (
            <PhoneCard
              key={device.slug}
              device={device}
              selected={compareSlugs.includes(device.slug)}
              onSelect={() => toggleCompare(device)}
              onOpen={() => setActiveSlug(device.slug)}
            />
          ))}
        </div>
        {deviceCount > 0 && (
          <div className="catalog-more" aria-live="polite">
            <span>Showing {devices.length.toLocaleString("en-PK")} of {deviceCount.toLocaleString("en-PK")} phones</span>
            {devicesQuery.hasNextPage && <button type="button" disabled={devicesQuery.isFetchingNextPage} onClick={() => void devicesQuery.fetchNextPage()}>{devicesQuery.isFetchingNextPage ? "Loading more phones…" : "Load more phones ↓"}</button>}
            {devicesQuery.isFetchNextPageError && <div className="state-message error" role="alert">More phones couldn't load. <button type="button" className="retry-button" onClick={() => void devicesQuery.fetchNextPage()}>Retry</button></div>}
          </div>
        )}
      </section>
      <section className="value-strip" id="how-it-works" aria-label="Why use Phone Discover">
        <div><span className="value-index">01</span><strong>Built around your budget</strong><p>Start with what you can spend, not endless spec sheets.</p></div>
        <div><span className="value-index">02</span><strong>Price context, not hype</strong><p>See observed PKR asking prices with source and date context.</p></div>
        <div><span className="value-index">03</span><strong>Compare the trade-offs</strong><p>Shortlist up to three phones and review them side by side.</p></div>
      </section>
      <PakistanMarket onOpenDevice={setActiveSlug} onCompareDevice={addComparison}
        onResearchWeb={(marketFilters) => setMarketResearchRequest((previous) => ({ id: (previous?.id ?? 0) + 1, filters: marketFilters }))} />
      <footer className="site-footer"><div><a className="footer-brand" href="#top">phone<span>discover</span>.</a><p>Know your options. Choose on your terms.</p></div><div className="footer-links"><a href="#catalog">Explore phones</a><a href="#market">Pakistan prices</a><a href="#catalog">Phone catalog</a><a href="/admin/">Admin</a></div><p className="footer-note">PKR market prices are observed asking prices, not guaranteed offers. Reference catalog offers may use other currencies. Verify condition, PTA status and sellers independently.</p></footer>
      <AssistantDrawer
        marketResearchRequest={marketResearchRequest}
        onOpenDevice={(slug) => setActiveSlug(slug)}
        onCompareDevice={addComparison}
      />
      <ComparisonTray
        devices={compareDevices}
        selectionCount={compareSlugs.length}
        notice={comparisonNotice}
        loading={comparisonLoading}
        onRemove={removeComparison}
        onClear={() => { setCompareSlugs([]); setComparisonNotice(""); }}
        onCompare={() => setShowComparison(true)}
      />
      {showComparison && (
        <ComparisonModal
          devices={compareDevices}
          loading={comparisonLoading}
          onClose={() => setShowComparison(false)}
          onRemove={removeComparison}
          onOpenDevice={(slug) => {
            setShowComparison(false);
            setActiveSlug(slug);
          }}
        />
      )}
      {activeSlug && activeQuery.isPending && <div className="detail-backdrop" role="presentation"><div className="detail-load-state" role="status"><p>Loading phone details…</p><button type="button" onClick={() => setActiveSlug(null)}>Close</button></div></div>}
      {activeSlug && activeQuery.isError && <div className="detail-backdrop" role="presentation"><div className="detail-load-state" role="alert"><p>We couldn't load this phone's details.</p><div><button type="button" onClick={() => void activeQuery.refetch()}>Try again</button><button type="button" onClick={() => setActiveSlug(null)}>Close</button></div></div></div>}
      {activeQuery.data && activeSlug && <PhoneDetail device={activeQuery.data} onClose={() => setActiveSlug(null)} />}
    </main>
  );
}
