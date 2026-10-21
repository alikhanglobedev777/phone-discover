import type { Brand } from "../types";

type Props = {
  brands: Brand[];
  activeBrand: string;
  onSelect: (slug: string) => void;
};

export function BrandTabs({ brands, activeBrand, onSelect }: Props) {
  return (
    <div className="brand-tabs-section" aria-label="Browse smartphones by brand">
      <div className="brand-tabs-heading">
        <span>Explore by brand</span>
        <span>Switch brands or browse everything together</span>
      </div>
      <div className="brand-tabs" role="group" aria-label="Phone manufacturers">
        <button type="button" aria-pressed={!activeBrand}
          className={`brand-tab${!activeBrand ? " brand-tab-active" : ""}`}
          onClick={() => onSelect("")}>
          All brands <span aria-hidden="true">↗</span>
        </button>
        {brands.map((brand) => (
          <button type="button" key={brand.id} aria-pressed={activeBrand === brand.slug}
            className={`brand-tab${activeBrand === brand.slug ? " brand-tab-active" : ""}`}
            onClick={() => onSelect(brand.slug)}>
            {brand.name}
          </button>
        ))}
      </div>
    </div>
  );
}
