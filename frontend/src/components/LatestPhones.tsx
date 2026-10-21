import { useState } from "react";
import type { Device } from "../types";
import { selectLatestPhones } from "../lib/latestPhones";

type Props = {
  phones: Device[];
  isLoading: boolean;
  isError: boolean;
  onRetry: () => void;
  onOpen: (slug: string) => void;
};

const FALLBACK = "/phone-photo-pending.svg";

function LatestPhoneTile({ phone, onOpen }: { phone: Device; onOpen: (slug: string) => void }) {
  const [imageFailed, setImageFailed] = useState(false);
  const dateLabel = phone.release_date
    ? new Date(`${phone.release_date}T00:00:00`).toLocaleDateString("en-PK", {
      month: "short", year: "numeric",
    })
    : "";

  return (
    <button type="button" className="latest-phone-tile" onClick={() => onOpen(phone.slug)}
      aria-label={`View ${phone.brand.name} ${phone.name} details`}>
      <span className="latest-phone-photo">
        <img src={!imageFailed && phone.primary_image_url ? phone.primary_image_url : FALLBACK}
          alt={phone.primary_image_url && !imageFailed ? `${phone.brand.name} ${phone.name}` : "Product photo not available"}
          loading="lazy" onError={() => setImageFailed(true)} />
      </span>
      <span className="latest-phone-copy">
        <span className="latest-phone-brand">{phone.brand.name}</span>
        <strong>{phone.name}</strong>
        <span className="latest-phone-bottom"><span>{dateLabel}</span><span aria-hidden="true">↗</span></span>
      </span>
    </button>
  );
}

export function LatestPhones({ phones, isLoading, isError, onRetry, onOpen }: Props) {
  const latest = selectLatestPhones(phones);
  return (
    <section className="latest-section" id="latest" aria-labelledby="latest-heading">
      <div className="latest-heading-row">
        <div>
          <p className="eyebrow">Fresh from the catalog</p>
          <h2 id="latest-heading">The latest phones<span>.</span></h2>
          <p className="latest-intro">Recent releases with product photos and recorded dates. Pakistan availability may vary.</p>
        </div>
        <a href="#catalog" className="latest-explore-link">Explore the full catalog <span aria-hidden="true">↗</span></a>
      </div>
      {isLoading && <p className="latest-state" role="status">Finding the latest released models…</p>}
      {isError && <div className="latest-state" role="alert">Latest phones couldn't load. <button type="button" onClick={onRetry}>Try again</button></div>}
      {!isLoading && !isError && !latest.length && (
        <p className="latest-state">No phones with verified release dates are available yet. <a href="#catalog">Browse all phones</a>.</p>
      )}
      {latest.length > 0 && (
        <div className="latest-phone-grid">
          {latest.map((phone) => <LatestPhoneTile key={phone.slug} phone={phone} onOpen={onOpen} />)}
        </div>
      )}
      <p className="latest-source-note">Sorted by recorded release date, not by listing date or paid placement.</p>
    </section>
  );
}
