import type { Brand, DeviceFilters } from "../types";
import type { PhoneSearchEntry } from "../lib/catalogSearch";
import { PhoneSearchResults } from "./PhoneSearchResults";

type Props = {
  brands: Brand[];
  filters: DeviceFilters;
  onChange: (filters: DeviceFilters) => void;
  onReset: () => void;
  searchMatches: PhoneSearchEntry[];
  searchReady: boolean;
  onOpenPhone: (slug: string) => void;
};

export function CatalogFilters({ brands, filters, onChange, onReset, searchMatches, searchReady, onOpenPhone }: Props) {
  function update(name: keyof DeviceFilters, value: string) {
    onChange({ ...filters, [name]: value });
  }

  const activeCount = Object.values(filters).filter(Boolean).length;
  const advancedCount = ["status", "ram_min", "storage_min", "camera_score_min", "gaming_score_min", "country"]
    .filter((key) => Boolean(filters[key as keyof DeviceFilters])).length;

  return (
    <aside className="filter-panel" aria-label="Phone filters">
      <div className="filter-panel-heading">
        <div>
          <p className="eyebrow">Discover your fit</p>
          <h3>Find the right model</h3>
        </div>
        <button className="filter-reset" type="button" onClick={onReset} disabled={!activeCount}>
          Clear filters {activeCount ? `(${activeCount})` : ""}
        </button>
      </div>
      <div className="filter-main-row">
        <label className="filter-field filter-search-field">
          <span>Search phones</span>
          <input
            type="search"
            value={filters.search}
            onChange={(event) => update("search", event.target.value)}
            placeholder="iPhone, Samsung, Redmi…"
          />
        </label>
        <label className="filter-field">
          <span>Brand</span>
          <select value={filters.brand} onChange={(event) => update("brand", event.target.value)}>
            <option value="">All brands</option>
            {brands.map((brand) => <option key={brand.slug} value={brand.slug}>{brand.name}</option>)}
          </select>
        </label>
      </div>
      {filters.search.trim() && (
        <div className="catalog-search-suggestions">
          <PhoneSearchResults query={filters.search} entries={searchMatches}
            ready={searchReady} onOpen={onOpenPhone} />
        </div>
      )}
      <details className="filter-advanced">
        <summary>More filters {advancedCount ? `· ${advancedCount} applied` : ""}<span aria-hidden="true">⌄</span></summary>
        <div className="filter-grid">
          <label className="filter-field">
            <span>Availability</span>
            <select value={filters.status} onChange={(event) => update("status", event.target.value)}>
              <option value="">Any status</option>
              <option value="available">Available</option>
              <option value="announced">Announced</option>
              <option value="rumored">Rumored</option>
              <option value="discontinued">Discontinued</option>
            </select>
          </label>
          <label className="filter-field">
            <span>Minimum RAM</span>
            <select value={filters.ram_min} onChange={(event) => update("ram_min", event.target.value)}>
              <option value="">Any RAM</option>
              <option value="6">6 GB+</option>
              <option value="8">8 GB+</option>
              <option value="12">12 GB+</option>
              <option value="16">16 GB+</option>
            </select>
          </label>
          <label className="filter-field">
            <span>Minimum storage</span>
            <select value={filters.storage_min} onChange={(event) => update("storage_min", event.target.value)}>
              <option value="">Any storage</option>
              <option value="128">128 GB+</option>
              <option value="256">256 GB+</option>
              <option value="512">512 GB+</option>
              <option value="1024">1 TB+</option>
            </select>
          </label>
          <label className="filter-field">
            <span>Camera score</span>
            <select value={filters.camera_score_min} onChange={(event) => update("camera_score_min", event.target.value)}>
              <option value="">Any score</option>
              <option value="70">70+</option>
              <option value="80">80+</option>
              <option value="90">90+</option>
            </select>
          </label>
          <label className="filter-field">
            <span>Gaming score</span>
            <select value={filters.gaming_score_min} onChange={(event) => update("gaming_score_min", event.target.value)}>
              <option value="">Any score</option>
              <option value="70">70+</option>
              <option value="80">80+</option>
              <option value="90">90+</option>
            </select>
          </label>
          <label className="filter-field">
            <span>Offer country</span>
            <select value={filters.country} onChange={(event) => update("country", event.target.value)}>
              <option value="">Any country</option>
              <option value="US">United States</option>
              <option value="PK">Pakistan</option>
              <option value="GB">United Kingdom</option>
              <option value="AE">United Arab Emirates</option>
              <option value="IN">India</option>
            </select>
          </label>
        </div>
        <p className="catalog-filter-note">Searching under a PKR budget? <a href="#market">Use the Pakistan market search</a>. International reference offers are in different currencies.</p>
      </details>
    </aside>
  );
}
