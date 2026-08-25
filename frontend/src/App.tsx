import { useDeferredValue, useEffect, useMemo, useState } from "react";
import { useQueries, useQuery } from "@tanstack/react-query";
import { getBrands, getDevice, getDevices } from "./lib/api";
import { CatalogFilters } from "./components/CatalogFilters";
import { ComparisonModal } from "./components/ComparisonModal";
import { ComparisonTray } from "./components/ComparisonTray";
import { PhoneCard } from "./components/PhoneCard";
import { PhoneDetail } from "./components/PhoneDetail";
import { RecommendationAssistant } from "./components/RecommendationAssistant";
import type { Device, DeviceFilters } from "./types";

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
    localStorage.removeItem(COMPARISON_STORAGE_KEY);
  }
  return [];
}

export default function App() {
  const [filters, setFilters] = useState<DeviceFilters>(EMPTY_FILTERS);
  const [activeSlug, setActiveSlug] = useState<string | null>(() => new URLSearchParams(window.location.search).get("device"));
  const [compareSlugs, setCompareSlugs] = useState<string[]>(initialComparisonSlugs);
  const [showComparison, setShowComparison] = useState(
    () => (new URLSearchParams(window.location.search).get("compare")?.split(",").filter(Boolean).length ?? 0) >= 2,
  );
  const deferredSearch = useDeferredValue(filters.search);
  const queryFilters = useMemo(
    () => ({ ...filters, search: deferredSearch }),
    [deferredSearch, filters],
  );
  const devicesQuery = useQuery({
    queryKey: ["devices", queryFilters],
    queryFn: () => getDevices(queryFilters),
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
  const devices = devicesQuery.data?.results ?? [];
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
    setCompareSlugs((current) => {
      if (current.includes(device.slug)) return current.filter((slug) => slug !== device.slug);
      if (current.length >= 3) return current;
      return [...current, device.slug];
    });
  }

  function removeComparison(slug: string) {
    setCompareSlugs((current) => current.filter((item) => item !== slug));
  }

  function addComparison(slug: string) {
    setCompareSlugs((current) => {
      if (current.includes(slug) || current.length >= 3) return current;
      return [...current, slug];
    });
  }

  return (
    <main className="shell">
      <nav className="nav">
        <div className="brand-mark">Mobile Discovery</div>
        <div className="nav-actions">
          <a className="nav-link" href="/admin/">Admin</a>
          <a className="nav-link" href="#assistant">AI assistant</a>
        </div>
      </nav>
      <section className="hero">
        <p className="eyebrow">Smartphone discovery</p>
        <h1>Find the phone that fits your life.</h1>
        <p className="hero-copy">
          A trustworthy catalog and recommendation assistant for camera, gaming, battery, and value.
        </p>
        <a className="hero-cta" href="#catalog">Explore phones <span aria-hidden="true">↓</span></a>
      </section>
      <section className="catalog-section" id="catalog">
        <CatalogFilters
          brands={brandsQuery.data?.results ?? []}
          filters={filters}
          onChange={setFilters}
          onReset={() => setFilters(EMPTY_FILTERS)}
        />
        <div className="section-heading">
          <div>
            <p className="eyebrow">Explore the catalog</p>
            <h2>{Object.values(filters).some(Boolean) ? "Phones matching your filters" : "Popular phones"}</h2>
          </div>
          <span className="muted">{devicesQuery.data?.count ?? 0} phones</span>
        </div>
        {devicesQuery.isLoading && <p className="state-message">Loading phones…</p>}
        {devicesQuery.isError && <p className="state-message error">Could not load the catalog. Is the backend running?</p>}
        {!devicesQuery.isLoading && !devices.length && (
          <div className="empty-state">
            <strong>No matching phones</strong>
            <p>Try clearing one or more filters, or add more devices from the admin panel.</p>
            <button type="button" onClick={() => setFilters(EMPTY_FILTERS)}>Clear all filters</button>
          </div>
        )}
        <div className="phone-grid">
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
      </section>
      <RecommendationAssistant onOpenDevice={setActiveSlug} onCompareDevice={addComparison} />
      <ComparisonTray
        devices={compareDevices}
        selectionCount={compareSlugs.length}
        loading={comparisonLoading}
        onRemove={removeComparison}
        onClear={() => setCompareSlugs([])}
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
      {activeQuery.data && <PhoneDetail device={activeQuery.data} onClose={() => setActiveSlug(null)} />}
    </main>
  );
}
