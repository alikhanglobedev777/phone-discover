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
