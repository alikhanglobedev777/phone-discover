import { useEffect, useMemo, useState } from "react";
import type { Device } from "../types";

type Props = { device: Device; onClose: () => void };

export function PhoneDetail({ device, onClose }: Props) {
  const [variantId, setVariantId] = useState<number | null>(device.variants?.[0]?.id ?? null);
  const [activeImage, setActiveImage] = useState(device.primary_image_url || device.images?.[0]?.image_url || "");
  const variant = useMemo(
    () => device.variants?.find((item) => item.id === variantId) ?? device.variants?.[0],
    [device.variants, variantId],
  );

  useEffect(() => {
    setVariantId(device.variants?.[0]?.id ?? null);
    setActiveImage(device.primary_image_url || device.images?.[0]?.image_url || "");
  }, [device]);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handleKeyDown);
    document.body.classList.add("modal-open");
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.classList.remove("modal-open");
    };
  }, [onClose]);

  const imageAlt = device.images?.find((image) => image.image_url === activeImage)?.alt_text;

  return (
    <div className="detail-backdrop" role="presentation" onClick={onClose}>
      <section className="detail-panel" role="dialog" aria-modal="true" aria-labelledby="phone-detail-title" onClick={(event) => event.stopPropagation()}>
        <button className="close-button" onClick={onClose} aria-label="Close details">×</button>
        <div className="detail-hero">
          <div className="detail-gallery">
            <div className="detail-image-stage">
              {activeImage ? (
                <img src={activeImage} alt={imageAlt || `${device.brand.name} ${device.name}`} />
              ) : (
                <span aria-hidden="true">{device.brand.name.slice(0, 1)}</span>
              )}
            </div>
            {(device.images?.length ?? 0) > 1 && (
              <div className="detail-thumbnails" aria-label="Phone images">
                {device.images?.map((image) => (
                  <button
                    type="button"
                    className={activeImage === image.image_url ? "active" : ""}
                    onClick={() => setActiveImage(image.image_url)}
                    key={image.id}
                  >
                    <img src={image.image_url} alt={image.alt_text || "Phone view"} />
                  </button>
                ))}
              </div>
            )}
          </div>
          <div className="detail-intro">
            <div className="detail-badges">
              <span className={`status-badge status-${device.status}`}>{device.status}</span>
              {device.release_date && <span className="soft-badge">{device.release_date}</span>}
            </div>
            <p className="eyebrow">{device.brand.name}</p>
            <h2 id="phone-detail-title">{device.name}</h2>
            <p className="detail-summary">{device.summary}</p>
            {device.data_source === "web_research" && <p className="pk-evidence-note">Web-researched specifications and prices are source-reported and await independent review.</p>}
            <dl className="detail-facts">
              <div><dt>Operating system</dt><dd>{device.operating_system || "Not specified"}</dd></div>
              <div><dt>Starting price</dt><dd>{device.lowest_price ? `${device.lowest_price.currency} ${device.lowest_price.price}` : "Unavailable"}</dd></div>
              <div><dt>Availability</dt><dd>{device.status}</dd></div>
            </dl>
            {device.official_url && (
              <a className="official-link" href={device.official_url} target="_blank" rel="noreferrer">Official product page ↗</a>
            )}
          </div>
        </div>

        {variant && (
          <section className="variant-section">
            <div className="detail-section-heading">
              <div><p className="eyebrow">Configuration</p><h3>Performance snapshot</h3></div>
              {(device.variants?.length ?? 0) > 1 && (
                <select value={variant.id} onChange={(event) => setVariantId(Number(event.target.value))} aria-label="Phone variant">
                  {device.variants?.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}
                </select>
              )}
            </div>
            <div className="spec-grid">
              <div><span>Memory</span><strong>{variant.ram_gb} GB RAM / {variant.storage_gb} GB</strong></div>
              <div><span>Battery</span><strong>{variant.battery_mah ? `${variant.battery_mah} mAh` : "—"}</strong></div>
              <div><span>Display</span><strong>{variant.display_refresh_hz ? `${variant.display_refresh_hz} Hz` : "—"}</strong></div>
              <div><span>Chipset</span><strong>{variant.chipset || "—"}</strong></div>
            </div>
            <div className="score-grid">
              {[
                ["Camera", variant.camera_score],
                ["Gaming", variant.gaming_score],
                ["Battery", variant.battery_score],
              ].map(([label, score]) => (
                <div className="score-row" key={label}>
                  <span>{label}</span>
                  <div><i style={{ width: `${Math.min(100, Number(score))}%` }} /></div>
                  <strong>{Number(score).toFixed(0)}</strong>
                </div>
              ))}
            </div>
          </section>
        )}

        {(device.specification_sections?.length ?? 0) > 0 && (
          <section className="structured-specs">
            <div className="detail-section-heading">
              <div><p className="eyebrow">Full specification</p><h3>Everything you need to know</h3></div>
            </div>
            {device.specification_sections?.map((section) => (
              <div className="spec-section" key={section.id}>
                <h4>{section.name}</h4>
                <dl>
                  {section.items.map((item) => (
                    <div key={item.id}><dt>{item.label}</dt><dd>{item.value}</dd></div>
                  ))}
                </dl>
              </div>
            ))}
          </section>
        )}

        <section className="offers-section">
          <div className="detail-section-heading">
            <div><p className="eyebrow">Where to buy</p><h3>Available offers</h3></div>
          </div>
          <div className="offer-list">
            {variant?.offers?.filter((offer) => offer.is_available).map((offer) => (
              <a className="offer-row" href={offer.product_url} target="_blank" rel="noreferrer" key={offer.id}>
                <span><strong>{offer.seller_name}</strong><small>{offer.country_code}{offer.is_affiliate ? " · Affiliate link" : ""}</small></span>
                <b>{offer.currency} {offer.price} ↗</b>
              </a>
            ))}
            {!variant?.offers?.some((offer) => offer.is_available) && <p className="muted">No active offers for this configuration.</p>}
          </div>
        </section>
      </section>
    </div>
  );
}
