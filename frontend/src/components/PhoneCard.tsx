import type { Device } from "../types";

type Props = {
  device: Device;
  selected: boolean;
  onSelect: () => void;
  onOpen: () => void;
};

export function PhoneCard({ device, selected, onSelect, onOpen }: Props) {
  const releaseYear = device.release_date?.slice(0, 4);

  return (
    <article className={`phone-card ${selected ? "phone-card-selected" : ""}`}>
      <div className="phone-art">
        {device.primary_image_url ? (
          <img src={device.primary_image_url} alt={`${device.brand.name} ${device.name}`} loading="lazy" />
        ) : (
          <span aria-hidden="true">{device.brand.name.slice(0, 1)}</span>
        )}
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
        <label className={`compare-check ${selected ? "compare-check-selected" : ""}`}>
          <input type="checkbox" checked={selected} onChange={onSelect} />
          {selected ? "Added to comparison" : "Add to comparison"}
        </label>
      </div>
    </article>
  );
}
