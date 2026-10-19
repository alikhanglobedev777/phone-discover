import { useMemo, useState } from "react";
import { canCompareStartingPrices } from "../lib/comparison";
import { useModalKeyboard } from "../lib/useModalKeyboard";
import type { CSSProperties, ReactNode } from "react";
import type { Device, Variant } from "../types";

type Props = {
  devices: Device[];
  loading: boolean;
  onClose: () => void;
  onRemove: (slug: string) => void;
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

export function ComparisonModal({ devices, loading, onClose, onRemove, onOpenDevice }: Props) {
  const [shareStatus, setShareStatus] = useState("");
  const canComparePrices = canCompareStartingPrices(devices);
  const dialogRef = useModalKeyboard<HTMLElement>(onClose);
  const gridStyle = {
    gridTemplateColumns: `150px repeat(${Math.max(devices.length, 2)}, minmax(190px, 1fr))`,
  };

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

  if (loading && devices.length < 2) {
    return (
      <div className="comparison-backdrop" role="presentation" onClick={onClose}>
        <section ref={dialogRef} tabIndex={-1} className="comparison-modal comparison-modal-loading" role="dialog" aria-modal="true" aria-label="Comparison loading" onClick={(event) => event.stopPropagation()}>
          <p>Loading comparison…</p>
        </section>
      </div>
    );
  }

  if (devices.length < 2) {
    return (
      <div className="comparison-backdrop" role="presentation" onClick={onClose}>
        <section ref={dialogRef} tabIndex={-1} className="comparison-modal comparison-modal-loading" role="dialog" aria-modal="true" aria-label="Comparison unavailable" onClick={(event) => event.stopPropagation()}>
          <div className="comparison-unavailable">
            <strong>Comparison unavailable</strong>
            <p>One or more selected phones could not be loaded. Clear the shortlist and try again.</p>
            <button type="button" onClick={onClose}>Close</button>
          </div>
        </section>
      </div>
    );
  }

  return (
    <div className="comparison-backdrop" role="presentation" onClick={onClose}>
      <section ref={dialogRef} tabIndex={-1} className="comparison-modal" role="dialog" aria-modal="true" aria-labelledby="comparison-title" onClick={(event) => event.stopPropagation()}>
        <header className="comparison-modal-header">
          <div>
            <p className="eyebrow">Side-by-side decision</p>
            <h2 id="comparison-title">Compare your shortlist</h2>
            <p>Comparable specifications are highlighted from catalog data. Prices in different currencies are never ranked against each other.</p>{shareStatus && <p role="status" className="share-status">{shareStatus}</p>}
          </div>
          <div className="comparison-header-actions">
            <button type="button" onClick={copyShareLink}>Copy share link</button>
            <button className="comparison-modal-close" type="button" onClick={onClose} aria-label="Close comparison">×</button>
          </div>
        </header>

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

          <div className="comparison-group-title">Core hardware</div>
          <ComparisonRow label="RAM" best="max" style={gridStyle} cells={devices.map((device) => ({ content: `${mainVariant(device)?.ram_gb ?? "—"} GB`, numeric: mainVariant(device)?.ram_gb }))} />
          <ComparisonRow label="Storage" best="max" style={gridStyle} cells={devices.map((device) => ({ content: `${mainVariant(device)?.storage_gb ?? "—"} GB`, numeric: mainVariant(device)?.storage_gb }))} />
          <ComparisonRow label="Chipset" style={gridStyle} cells={devices.map((device) => ({ content: mainVariant(device)?.chipset ?? "—" }))} />
          <ComparisonRow label="Refresh rate" best="max" style={gridStyle} cells={devices.map((device) => ({ content: mainVariant(device)?.display_refresh_hz ? `${mainVariant(device)?.display_refresh_hz} Hz` : "—", numeric: mainVariant(device)?.display_refresh_hz }))} />
          <ComparisonRow label="Battery" best="max" style={gridStyle} cells={devices.map((device) => ({ content: mainVariant(device)?.battery_mah ? `${mainVariant(device)?.battery_mah} mAh` : "—", numeric: mainVariant(device)?.battery_mah }))} />

          <div className="comparison-group-title">Scores</div>
          <ComparisonRow label="Camera" best="max" style={gridStyle} cells={devices.map((device) => ({ content: `${Number(mainVariant(device)?.camera_score ?? 0).toFixed(0)}/100`, numeric: Number(mainVariant(device)?.camera_score ?? 0) }))} />
          <ComparisonRow label="Gaming" best="max" style={gridStyle} cells={devices.map((device) => ({ content: `${Number(mainVariant(device)?.gaming_score ?? 0).toFixed(0)}/100`, numeric: Number(mainVariant(device)?.gaming_score ?? 0) }))} />
          <ComparisonRow label="Battery score" best="max" style={gridStyle} cells={devices.map((device) => ({ content: `${Number(mainVariant(device)?.battery_score ?? 0).toFixed(0)}/100`, numeric: Number(mainVariant(device)?.battery_score ?? 0) }))} />

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
      </section>
    </div>
  );
}
