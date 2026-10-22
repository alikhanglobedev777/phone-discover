/** Small, versioned browser cache for published phone names (never prices). */
export type PhoneSearchEntry = {
  slug: string;
  name: string;
  brand: string;
  brand_slug: string;
  image_url: string;
};

type StoredIndex = {
  version: number;
  savedAt: number;
  entries: PhoneSearchEntry[];
};

const KEY = "phone-discover-search-index-v1";
const VERSION = 1;
const MAX_CACHE_AGE_MS = 7 * 24 * 60 * 60 * 1000;

export function readCachedSearchIndex(): StoredIndex | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return null;
    const saved = JSON.parse(raw) as StoredIndex;
    if (saved.version !== VERSION || !Array.isArray(saved.entries) ||
        !Number.isFinite(saved.savedAt) || saved.savedAt > Date.now() ||
        Date.now() - saved.savedAt > MAX_CACHE_AGE_MS ||
        saved.entries.length > 10000 ||
        !saved.entries.every((entry) =>
          typeof entry.slug === "string" && typeof entry.name === "string" &&
          typeof entry.brand === "string" && typeof entry.brand_slug === "string" &&
          typeof entry.image_url === "string")) {
      window.localStorage.removeItem(KEY);
      return null;
    }
    return saved;
  } catch {
    return null; // Private browsing / storage disabled: network search still works.
  }
}

export function storeSearchIndex(entries: PhoneSearchEntry[], savedAt = Date.now()) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(KEY, JSON.stringify({
      version: VERSION,
      savedAt,
      entries,
    } satisfies StoredIndex));
  } catch {
    // Quota exceeded or storage disabled: keep working with in-memory React Query.
  }
}

/** Fast local suggestions; server-side filtering remains authoritative. */
export function searchCachedPhones(
  entries: PhoneSearchEntry[],
  query: string,
  brandSlug = "",
  limit = 8,
): PhoneSearchEntry[] {
  const terms = query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
  if (!terms.length) return [];
  const scored: { entry: PhoneSearchEntry; score: number }[] = [];
  for (const entry of entries) {
    if (brandSlug && brandSlug !== entry.brand_slug) continue;
    const name = entry.name.toLocaleLowerCase();
    const combined = (entry.brand + " " + entry.name).toLocaleLowerCase();
    if (!terms.every((term) => combined.includes(term))) continue;
    const fullQuery = terms.join(" ");
    const score = name === fullQuery ? 0
      : name.startsWith(fullQuery) ? 1
      : combined.startsWith(fullQuery) ? 2
      : name.includes(fullQuery) ? 3 : 4;
    scored.push({ entry, score });
  }
  scored.sort((a, b) =>
    a.score - b.score || a.entry.name.length - b.entry.name.length ||
    a.entry.name.localeCompare(b.entry.name));
  return scored.slice(0, Math.max(0, limit)).map(({ entry }) => entry);
}
