import type { Brand, Device, DeviceFilters, Paginated } from "../types";
import { apiUrl } from "./apiUrl.ts";

async function request<T>(url: string): Promise<T> {
  const response = await fetch(apiUrl(url));
  if (!response.ok) throw new Error(`Request failed: ${response.status}`);
  return response.json() as Promise<T>;
}

export function getDevices(filters: DeviceFilters, page = 1) {
  const query = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value.trim()) query.set(key, value.trim());
  });
  query.set("page", String(page));
  return request<Paginated<Device>>(`/api/catalog/devices/?${query.toString()}`);
}

export function getDevice(slug: string) {
  return request<Device>(`/api/catalog/devices/${encodeURIComponent(slug)}/`);
}

export function getBrands() {
  return request<Paginated<Brand>>("/api/catalog/brands/?ordering=name");
}

export type ComparisonLookupResult = {
  status: string;
  notice: string;
  saved?: { devices_created?: number; prices_saved?: number; rejected?: number };
  sources: { url: string; title: string }[];
  devices: { slug: string; name: string; brand: string; primary_image_url: string; data_source: string }[];
};

export async function researchComparisonPhone(query: string, signal?: AbortSignal): Promise<ComparisonLookupResult> {
  const response = await fetch(apiUrl("/api/recommendations/compare-lookup/"), {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }), signal,
  });
  if (!response.ok) throw new Error(response.status === 429 ? "AI web research is temporarily rate-limited. Please try later." : `Research failed (${response.status}). Please retry.`);
  return response.json() as Promise<ComparisonLookupResult>;
}
