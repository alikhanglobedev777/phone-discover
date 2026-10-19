export type Offer = {
  id: number;
  country_code: string;
  currency: string;
  price: string;
  seller_name: string;
  product_url: string;
  is_affiliate: boolean;
  is_available: boolean;
};

export type Brand = {
  id: number;
  name: string;
  slug: string;
  logo_url: string;
};

export type DeviceImage = {
  id: number;
  image_url: string;
  alt_text: string;
  sort_order: number;
  is_primary: boolean;
  view?: "front" | "back" | "side" | "detail" | "unspecified";
  color?: number | null;
};

export type DeviceColor = {
  id: number;
  name: string;
  hex_code: string;
  sort_order: number;
};

export type SpecificationItem = {
  id: number;
  label: string;
  value: string;
  sort_order: number;
};

export type SpecificationSection = {
  id: number;
  name: string;
  slug: string;
  sort_order: number;
  items: SpecificationItem[];
};

export type DeviceStatus = "rumored" | "announced" | "available" | "discontinued";

export type Variant = {
  id: number;
  name: string;
  ram_gb: number;
  storage_gb: number;
  battery_mah: number | null;
  display_refresh_hz: number | null;
  chipset: string;
  camera_score: string;
  gaming_score: string;
  battery_score: string;
  offers: Offer[];
};

export type Device = {
  id: number;
  brand: Brand;
  name: string;
  slug: string;
  summary: string;
  data_source?: "catalog" | "web_research";
  status: DeviceStatus;
  release_date: string | null;
  operating_system: string;
  primary_image_url: string;
  lowest_price: { price: string; currency: string; country_code: string; evidence_type?: string } | null;
  official_url?: string;
  specifications?: Record<string, unknown>;
  specification_sections?: SpecificationSection[];
  images?: DeviceImage[];
  colors?: DeviceColor[];
  last_verified_at?: string | null;
  variants?: Variant[];
};

export type DeviceFilters = {
  search: string;
  brand: string;
  status: string;
  price_max: string;
  ram_min: string;
  storage_min: string;
  camera_score_min: string;
  gaming_score_min: string;
  country: string;
};

export type Paginated<T> = {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
};
