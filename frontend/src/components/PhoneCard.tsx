import { useEffect, useState } from "react";
import type { Device } from "../types";

type Props = {
  device: Device;
  selected: boolean;
  onSelect: () => void;
  onOpen: () => void;
};

const MISSING_PHOTO = "/phone-photo-pending.svg";

export function PhoneCard({ device, selected, onSelect, onOpen }: Props) {
  const releaseYear = device.release_date?.slice(0, 4);
  const [photoFailed, setPhotoFailed] = useState(false);
  useEffect(() => setPhotoFailed(false), [device.id, device.primary_image_url]);
  // Exact-model photo URL from the WhatMobile listing, with reuse permission
  // confirmed by the Phone Discover operator. Never substitute a Pro/Ultra photo.
  const approvedWhatMobilePhoto =
    device.brand.name.toLowerCase() === "xiaomi" && device.name === "12S Pro"
      ? "https://www.whatmobile.com.pk/admin/images/Xiaomi/Xiaomi12SPro-b.jpg"
      : "";
  const displayPhoto = device.primary_image_url?.trim() || approvedWhatMobilePhoto;
  const hasPhoto = Boolean(displayPhoto) && !photoFailed;
  const variantsCount = device.variants_count ?? device.variants?.length ?? 0;
  const colors = device.colors ?? [];

  return (
    <article className={`phone-card ${selected ? "phone-card-selected" : ""}`}>
      <div className="phone-art">
        <img
          src={hasPhoto ? displayPhoto : MISSING_PHOTO}
          alt={hasPhoto ? `${device.brand.name} ${device.name}` : "Phone photo not yet available"}
          loading="lazy"
          onError={() => setPhotoFailed(true)}
        />
        {!hasPhoto && <span className="photo-pending-label">Photo pending</span>}
        <span className={`status-badge status-${device.status}`}>{device.status}</span>
      </div>
      <div className="phone-card-body">
        <div className="phone-meta-line">
          <p className="muted">{device.brand.name}</p>
          {releaseYear && <span>{releaseYear}</span>}
        </div>
        <h3>{device.name}</h3>
        {device.data_source === "web_research" && <p className="pk-evidence-note">Web researched · source-reported facts</p>}
        <p className="card-summary">{device.summary}</p>
        <div className="phone-chips">
          {device.operating_system && <span>{device.operating_system}</span>}
          {device.lowest_price?.country_code && <span>{device.lowest_price.country_code} offer</span>}
        </div>
        {colors.length > 0 && (
          <div className="phone-card-colors" aria-label="Documented phone colors">
            {colors.slice(0, 5).map((color) => (
              <span key={color.id} className="phone-card-color" title={color.name}>
                <span
                  className={`phone-card-color-dot${color.hex_code ? "" : " no-color-hex"}`}
                  style={color.hex_code ? { backgroundColor: color.hex_code } : undefined}
                  aria-hidden="true"
                />
                <span>{color.name}</span>
              </span>
            ))}
            {colors.length > 5 && <span className="muted">+{colors.length - 5}</span>}
          </div>
        )}
        <div className="card-footer">
          <div className="price-block">
            <span>{device.lowest_price?.evidence_type ? "Observed asking price" : "Reference catalog offer"}</span>
            <strong>
              {device.lowest_price
                ? `${device.lowest_price.currency} ${device.lowest_price.price}`
                : "Price unavailable"}
            </strong>
          </div>
          <button className="text-button" type="button" onClick={onOpen} aria-label={`View details for ${device.name}`}>View details →</button>
        </div>
        <button
          className="phone-variants-button"
          type="button"
          onClick={onOpen}
          aria-label={`View ${variantsCount} RAM and storage variants for ${device.brand.name} ${device.name}`}
        >
          <span>Variants ({variantsCount})</span>
          <span aria-hidden="true">→</span>
        </button>
        <label className={`compare-check ${selected ? "compare-check-selected" : ""}`}>
          <input type="checkbox" checked={selected} onChange={onSelect} />
          {selected ? "Added to comparison" : "Add to comparison"}
        </label>
      </div>
    </article>
  );
}
