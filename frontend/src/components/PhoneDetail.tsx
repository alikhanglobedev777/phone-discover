import { useEffect, useMemo, useState } from "react";
import { galleryPhotos, photosForColor, viewLabel } from "../lib/deviceGallery";
import { useModalKeyboard } from "../lib/useModalKeyboard";
import type { Device } from "../types";

type Props = { device: Device; onClose: () => void };

export function PhoneDetail({ device, onClose }: Props) {
  const dialogRef = useModalKeyboard<HTMLElement>(onClose);
  const [variantId, setVariantId] = useState<number | null>(device.variants?.[0]?.id ?? null);
  const [colorId, setColorId] = useState<number | null>(null);
  const [activePhotoKey, setActivePhotoKey] = useState("");
  const [failedURLs, setFailedURLs] = useState<string[]>([]);
  const variant = useMemo(
    () => device.variants?.find((item) => item.id === variantId) ?? device.variants?.[0],
    [device.variants, variantId],
  );
  const allPhotos = useMemo(() => galleryPhotos(device), [device]);
  const photoSelection = useMemo(() => photosForColor(allPhotos, colorId), [allPhotos, colorId]);
  const visiblePhotos = useMemo(
    () => photoSelection.photos.filter((photo) => !failedURLs.includes(photo.url)),
    [photoSelection, failedURLs],
  );
  const activePhoto = visiblePhotos.find((photo) => photo.key === activePhotoKey) ?? visiblePhotos[0];
  const activeIndex = visiblePhotos.findIndex((photo) => photo.key === activePhoto?.key);
  const selectedColor = device.colors?.find((color) => color.id === colorId);
  const attribution = device.specifications?.photo_attribution as
    | { source?: string; license?: string; credit?: string } | undefined;

  useEffect(() => {
    setVariantId(device.variants?.[0]?.id ?? null);
    setColorId(null);
    setActivePhotoKey("");
    setFailedURLs([]);
  }, [device.id]);

  const navigatePhoto = (step: number) => {
    if (visiblePhotos.length < 2) return;
    const next = (activeIndex + step + visiblePhotos.length) % visiblePhotos.length;
    setActivePhotoKey(visiblePhotos[next].key);
  };

  return (
    <div className="detail-backdrop" role="presentation" onClick={onClose}>
      <section ref={dialogRef} tabIndex={-1} className="detail-panel" role="dialog" aria-modal="true" aria-labelledby="phone-detail-title" onClick={(event) => event.stopPropagation()}>
        <div className="detail-modal-toolbar">
          <span className="detail-modal-kicker">Phone details</span>
          <button type="button" className="close-button" onClick={onClose} aria-label="Close details">
            Close <span aria-hidden="true">×</span>
          </button>
        </div>
        <div className="detail-hero">
          <div className="detail-gallery" role="group" aria-label={`${device.brand.name} ${device.name} photo gallery`}>
            <div className="detail-image-stage">
              {activePhoto ? (
                <img
                  key={activePhoto.url}
                  src={activePhoto.url}
                  alt={activePhoto.alt}
                  onError={() => setFailedURLs((urls) => urls.includes(activePhoto.url) ? urls : [...urls, activePhoto.url])}
                />
              ) : (
                <div className="detail-gallery-empty" role="status">
                  <img src="/phone-photo-pending.svg" alt="Phone photo not yet verified" />
                  <p>{selectedColor ? `No verified photos for ${selectedColor.name}` : "Product photo awaiting verification"}</p>
                </div>
              )}
              {activePhoto && <span className="detail-view-badge">{viewLabel(activePhoto.view)}{activePhoto.color ? ` · ${device.colors?.find((color) => color.id === activePhoto.color)?.name ?? ""}` : ""}</span>}
              {visiblePhotos.length > 1 && (
                <div className="detail-gallery-navigation">
                  <button type="button" onClick={() => navigatePhoto(-1)} aria-label="Previous phone photo">‹</button>
                  <span aria-live="polite">{activeIndex + 1} / {visiblePhotos.length}</span>
                  <button type="button" onClick={() => navigatePhoto(1)} aria-label="Next phone photo">›</button>
                </div>
              )}
            </div>
            {visiblePhotos.length > 1 && (
              <div className="detail-thumbnails" aria-label="Available phone views">
                {visiblePhotos.map((photo, index) => (
                  <button
                    type="button"
                    className={activePhoto?.key === photo.key ? "active" : ""}
                    onClick={() => setActivePhotoKey(photo.key)}
                    aria-label={`Show ${viewLabel(photo.view).toLowerCase()} photo ${index + 1}`}
                    aria-pressed={activePhoto?.key === photo.key}
                    key={photo.key}
                  >
                    <img src={photo.url} alt="" loading="lazy" onError={() => setFailedURLs((urls) => urls.includes(photo.url) ? urls : [...urls, photo.url])} />
                    <span>{viewLabel(photo.view)}</span>
                  </button>
                ))}
              </div>
            )}
            {!!device.colors?.length && (
              <div className="detail-finish-picker">
                <div className="detail-finish-heading"><strong>Colors &amp; finishes</strong><span>{selectedColor?.name ?? "All photos"}</span></div>
                <div className="detail-finish-options" aria-label="Choose a phone finish">
                  <button type="button" className={colorId === null ? "selected" : ""} aria-pressed={colorId === null} onClick={() => { setColorId(null); setActivePhotoKey(""); }}>
                    <span className="detail-all-finishes" aria-hidden="true">◈</span> All
                  </button>
                  {device.colors.map((color) => (
                    <button type="button" key={color.id} className={colorId === color.id ? "selected" : ""} aria-pressed={colorId === color.id} onClick={() => { setColorId(color.id); setActivePhotoKey(""); }}>
                      <span className={`detail-color-chip${color.hex_code ? "" : " uncolored"}`} style={color.hex_code ? { backgroundColor: color.hex_code } : undefined} aria-hidden="true" />
                      {color.name}
                    </button>
                  ))}
                </div>
                {photoSelection.isRepresentative && (
                  <p className="detail-image-note">{visiblePhotos.length ? "Generic product photos shown; this finish may look different." : "No photograph of this finish is available yet."}</p>
                )}
              </div>
            )}
            {!device.colors?.length && <p className="detail-image-note">More angles and colors will appear when product photography is available.</p>}
            {attribution?.source?.startsWith("https://commons.wikimedia.org/") && (
              <p className="detail-image-note">
                Image: {attribution.credit ?? "Wikimedia Commons contributor"} · {attribution.license ?? "Source license"} ·{" "}
                <a href={attribution.source} target="_blank" rel="noreferrer">View source &amp; attribution ↗</a>
              </p>
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
