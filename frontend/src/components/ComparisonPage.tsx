import { useEffect, useMemo, useRef, useState } from "react";
import { safeSourceUrl } from "../lib/pakistan";
import { canCompareStartingPrices } from "../lib/comparison";
import { researchComparisonPhone } from "../lib/api";
import type { ComparisonLookupResult } from "../lib/api";
import type { CSSProperties, FormEvent, ReactNode } from "react";
import type { Device, Variant } from "../types";

type Props = {
  devices: Device[];
  loading: boolean;
  onClose: () => void;
  onRemove: (slug: string) => void;
  onAdd: (slug: string) => void;
  onOpenDevice: (slug: string) => void;
};

type ComparisonCell = {
  content: ReactNode;
  numeric?: number | null;
};

function mainVariant(device: Device): Variant | undefined {
  return device.variants?.[0];
}

function numericPrice(device: Device) {
  return device.lowest_price ? Number(device.lowest_price.price) : null;
}

function ComparisonRow({
  label,
  cells,
  best,
  style,
}: {
  label: string;
  cells: ComparisonCell[];
  best?: "min" | "max";
  style: CSSProperties;
}) {
  const numericValues = cells
    .map((cell) => cell.numeric)
    .filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  const bestValue = numericValues.length && best
    ? (best === "min" ? Math.min(...numericValues) : Math.max(...numericValues))
    : null;

  return (
    <div className="comparison-row" style={style}>
      <strong className="comparison-label">{label}</strong>
      {cells.map((cell, index) => {
        const isBest = bestValue !== null && cell.numeric === bestValue && numericValues.length > 1;
        return (
          <div className={`comparison-cell ${isBest ? "comparison-cell-best" : ""}`} key={index}>
            {isBest && <span className="best-marker">Best</span>}
            {cell.content || "—"}
          </div>
        );
      })}
    </div>
  );
}

export function ComparisonPage({ devices, loading, onClose, onRemove, onAdd, onOpenDevice }: Props) {
  const [shareStatus, setShareStatus] = useState("");
  const canComparePrices = canCompareStartingPrices(devices);
  const [query, setQuery] = useState("");
  const [phase, setPhase] = useState<"idle" | "local" | "web">("idle");
  const [found, setFound] = useState<ComparisonLookupResult["devices"]>([]);
  const [lookupNotice, setLookupNotice] = useState("");
  const [sources, setSources] = useState<ComparisonLookupResult["sources"]>([]);
  const requestRef = useRef<AbortController | null>(null);
  useEffect(() => () => requestRef.current?.abort(), []);
  const gridStyle = {
    gridTemplateColumns: `145px repeat(${Math.max(devices.length, 1)}, minmax(210px, 1fr))`,
  };

  async function searchPhone(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const term = query.trim();
    if (term.length < 3 || phase !== "idle") return;
    requestRef.current?.abort();
    const controller = new AbortController();
    requestRef.current = controller;
    setFound([]); setSources([]); setLookupNotice(""); setPhase("web");
    setLookupNotice("Checking the exact phone in your local catalog first. If missing, searching trusted source pages and saving verified prices…");
    try {
      // One endpoint owns both exact local lookup and the source-backed import.
      // Generic catalog search can return siblings (e.g. S24+ for S24 Ultra).
      const researched = await researchComparisonPhone(term, controller.signal);
      if (controller.signal.aborted) return;
      setFound(researched.devices);
      setSources(researched.sources);
      setLookupNotice(researched.notice || "No eligible exact phone model was found.");
    } catch (error) {
      if (!controller.signal.aborted) setLookupNotice(error instanceof Error ? error.message : "Search failed. Try again.");
    } finally {
      if (!controller.signal.aborted) setPhase("idle");
    }
  }

  const specificationRows = useMemo(() => {
    const labels = new Map<string, { section: string; sectionSlug: string; label: string }>();
    devices.forEach((device) => {
      device.specification_sections?.forEach((section) => {
        section.items.forEach((item) => {
          labels.set(`${section.slug}:${item.label}`, {
            section: section.name,
            sectionSlug: section.slug,
            label: item.label,
          });
        });
      });
    });
    return Array.from(labels.entries()).map(([key, definition]) => ({
      key,
      ...definition,
      values: devices.map((device) => {
        return device.specification_sections
          ?.find((section) => section.slug === definition.sectionSlug)
          ?.items.find((item) => item.label === definition.label)?.value ?? "—";
      }),
    }));
  }, [devices]);

  async function copyShareLink() {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setShareStatus("Link copied");
    } catch {
      setShareStatus("Copy unavailable. Copy the link from your browser address bar.");
    }
  }

  return (
    <section className="compare-page" aria-labelledby="comparison-title">
      <header className="comparison-modal-header">
        <div>
          <p className="eyebrow">Side-by-side decision</p>
          <h2 id="comparison-title">Compare phones with confidence.</h2>
          <p>Search the local catalog first. Missing phones can be researched online and saved when their source evidence passes validation.</p>
          {shareStatus && <p className="share-status" role="status">{shareStatus}</p>}
        </div>
        <div className="comparison-header-actions">
          <button type="button" onClick={copyShareLink}>Copy share link</button>
          <button type="button" onClick={onClose}>← Back to catalog</button>
        </div>
      </header>
      <form className="compare-search" onSubmit={(event) => void searchPhone(event)}>
        <label htmlFor="compare-phone-query">Find a phone to compare</label>
        <div className="compare-search-controls">
          <input id="compare-phone-query" type="search" value={query} minLength={3} maxLength={100}
            placeholder="e.g. Samsung Galaxy A57" disabled={phase !== "idle"}
            onChange={(event) => setQuery(event.target.value)} />
          <button type="submit" disabled={phase !== "idle" || query.trim().length < 3}>
            {phase === "local" ? "Checking catalog…" : phase === "web" ? "Researching web…" : "Search phone ↗"}
          </button>
        </div>
        <p className="compare-search-help">Source-reported research is not a verified offer, PTA approval, or live inventory.</p>
        {lookupNotice && <p className="compare-search-notice" role="status" aria-live="polite">{phase === "web" && <span className="compare-search-spinner" aria-hidden="true" />}{lookupNotice}</p>}
        {!!found.length && <div className="compare-search-results" aria-label="Phone search results">
          {found.map((phone) => <article key={phone.slug} className="compare-search-result">
            {phone.primary_image_url ? <img src={phone.primary_image_url} alt="" /> : <span className="compare-placeholder">PD</span>}
            <span><strong>{phone.brand} {phone.name}</strong><small>{phone.data_source === "web_research" ? "Source-reported · review before buying" : "Available in catalog"}</small></span>
            <button type="button" disabled={devices.some((device) => device.slug === phone.slug) || devices.length >= 3}
              onClick={() => onAdd(phone.slug)}>{devices.some((device) => device.slug === phone.slug) ? "Selected" : "+ Compare"}</button>
          </article>)}
        </div>}
        {!!sources.length && <div className="compare-sources"><strong>Research sources</strong> {sources.map((source) => { const url = safeSourceUrl(source.url); return url ? <a key={url} href={url} target="_blank" rel="noopener noreferrer">{source.title || "Source"} ↗</a> : null; })}</div>}
      </form>
      {loading && <p className="compare-placeholder-message" role="status">Loading your selected phones…</p>}
      {!devices.length && !loading && <div className="compare-placeholder-message"><strong>Your comparison starts here.</strong><p>Search for phones above, then select up to three to see a full side-by-side comparison.</p></div>}
      {!!devices.length && <>
        <div className="comparison-scroll">

          <div className="comparison-products" style={gridStyle}>
            <div className="comparison-label">Phones</div>
            {devices.map((device) => (
              <article className="comparison-product" key={device.slug}>
                <button className="comparison-remove" type="button" onClick={() => onRemove(device.slug)} aria-label={`Remove ${device.name}`}>×</button>
                <div className="comparison-product-image">
                  {device.primary_image_url ? <img src={device.primary_image_url} alt={`${device.brand.name} ${device.name}`} /> : <span>{device.brand.name[0]}</span>}
                </div>
                <small>{device.brand.name}</small>
                <h3>{device.name}</h3>
                <button className="comparison-details-link" type="button" onClick={() => onOpenDevice(device.slug)}>View full details</button>
              </article>
            ))}
          </div>

          <div className="comparison-group-title">Price and availability</div>
          <ComparisonRow label="Starting price" best={canComparePrices ? "min" : undefined} style={gridStyle} cells={devices.map((device) => ({
            content: device.lowest_price ? `${device.lowest_price.currency} ${device.lowest_price.price}` : "Unavailable",
            numeric: canComparePrices ? numericPrice(device) : null,
          }))} />
          {!canComparePrices && <div className="comparison-currency-note" role="note">Price highlights are disabled because offers are missing or use different currencies.</div>}
          <ComparisonRow label="Status" style={gridStyle} cells={devices.map((device) => ({ content: device.status }))} />
          <ComparisonRow label="Released" style={gridStyle} cells={devices.map((device) => ({ content: device.release_date ?? "—" }))} />
          <ComparisonRow label="Operating system" style={gridStyle} cells={devices.map((device) => ({ content: device.operating_system }))} />

          <div className="comparison-group-title">Configurations and finishes</div>
          <ComparisonRow label="RAM / storage options" style={gridStyle} cells={devices.map((device) => ({
            content: device.variants?.length
              ? [...device.variants]
                  .sort((a, b) => a.ram_gb - b.ram_gb || a.storage_gb - b.storage_gb)
                  .map((item) => `${item.ram_gb}GB / ${item.storage_gb === 1024 ? "1TB" : `${item.storage_gb}GB`}`)
                  .join(", ")
              : "Not documented",
          }))} />
          <ComparisonRow label="Documented colors" style={gridStyle} cells={devices.map((device) => ({
            content: device.colors?.length ? device.colors.map((color) => color.name).join(", ") : "Not documented",
          }))} />
          <div className="comparison-group-title">Core hardware</div>
          <ComparisonRow label="RAM" best="max" style={gridStyle} cells={devices.map((device) => ({ content: `${mainVariant(device)?.ram_gb ?? "—"} GB`, numeric: mainVariant(device)?.ram_gb }))} />
          <ComparisonRow label="Storage" best="max" style={gridStyle} cells={devices.map((device) => ({ content: `${mainVariant(device)?.storage_gb ?? "—"} GB`, numeric: mainVariant(device)?.storage_gb }))} />
          <ComparisonRow label="Chipset" style={gridStyle} cells={devices.map((device) => ({ content: mainVariant(device)?.chipset ?? "—" }))} />
          <ComparisonRow label="Refresh rate" best="max" style={gridStyle} cells={devices.map((device) => ({ content: mainVariant(device)?.display_refresh_hz ? `${mainVariant(device)?.display_refresh_hz} Hz` : "—", numeric: mainVariant(device)?.display_refresh_hz }))} />
          <ComparisonRow label="Battery" best="max" style={gridStyle} cells={devices.map((device) => ({ content: mainVariant(device)?.battery_mah ? `${mainVariant(device)?.battery_mah} mAh` : "—", numeric: mainVariant(device)?.battery_mah }))} />

          <div className="comparison-group-title">Scores</div>
          <ComparisonRow label="Camera" best="max" style={gridStyle} cells={devices.map((device) => ({ content: Number(mainVariant(device)?.camera_score ?? 0) > 0 ? `${Number(mainVariant(device)?.camera_score).toFixed(0)}/100` : "Not rated", numeric: Number(mainVariant(device)?.camera_score ?? 0) > 0 ? Number(mainVariant(device)?.camera_score) : null }))} />
          <ComparisonRow label="Gaming" best="max" style={gridStyle} cells={devices.map((device) => ({ content: Number(mainVariant(device)?.gaming_score ?? 0) > 0 ? `${Number(mainVariant(device)?.gaming_score).toFixed(0)}/100` : "Not rated", numeric: Number(mainVariant(device)?.gaming_score ?? 0) > 0 ? Number(mainVariant(device)?.gaming_score) : null }))} />
          <ComparisonRow label="Battery score" best="max" style={gridStyle} cells={devices.map((device) => ({ content: Number(mainVariant(device)?.battery_score ?? 0) > 0 ? `${Number(mainVariant(device)?.battery_score).toFixed(0)}/100` : "Not rated", numeric: Number(mainVariant(device)?.battery_score ?? 0) > 0 ? Number(mainVariant(device)?.battery_score) : null }))} />

          {specificationRows.length > 0 && <div className="comparison-group-title">Detailed specifications</div>}
          {specificationRows.map((row) => (
            <ComparisonRow
              label={`${row.section} · ${row.label}`}
              style={gridStyle}
              cells={row.values.map((value) => ({ content: value }))}
              key={row.key}
            />
          ))}
        </div>
      </>}
    </section>
  );
}
