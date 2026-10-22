import type { PhoneSearchEntry } from "../lib/catalogSearch";

type Props = {
  query: string;
  entries: PhoneSearchEntry[];
  ready: boolean;
  onOpen: (slug: string) => void;
};

export function PhoneSearchResults({ query, entries, ready, onOpen }: Props) {
  if (!query.trim()) return null;
  return (
    <div className="phone-search-results" aria-live="polite" aria-label="Local phone search suggestions">
      <div className="phone-search-results-title">
        <span>{ready ? "Quick matches from your phone catalog" : "Loading the phone search cache…"}</span>
        {ready && <small>{entries.length ? "Tap a phone to view details" : "Try another model name"}</small>}
      </div>
      {ready && entries.length === 0 && (
        <p className="phone-search-no-match">
          No matching phone names in the local index. The full catalog search may find specifications or other matches.
        </p>
      )}
      {ready && entries.length > 0 && (
        <div className="phone-search-result-list">
          {entries.map((entry) => (
            <button
              type="button"
              key={entry.slug}
              className="phone-search-result"
              onClick={() => onOpen(entry.slug)}
              aria-label={`View ${entry.brand} ${entry.name}`}
            >
              {entry.image_url ? (
                <img src={entry.image_url} alt="" loading="lazy" />
              ) : (
                <span className="phone-search-image-placeholder" aria-hidden="true">P.</span>
              )}
              <span className="phone-search-result-name">
                <strong>{entry.name}</strong>
                <small>{entry.brand}</small>
              </span>
              <span className="phone-search-result-arrow" aria-hidden="true">→</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
