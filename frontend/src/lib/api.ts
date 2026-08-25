import type { Brand, Device, DeviceFilters, Paginated } from "../types";

async function request<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Request failed: ${response.status}`);
  return response.json() as Promise<T>;
}

export function getDevices(filters: DeviceFilters) {
  const query = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value.trim()) query.set(key, value.trim());
  });
  const suffix = query.size ? `?${query.toString()}` : "";
  return request<Paginated<Device>>(`/api/catalog/devices/${suffix}`);
}

export function getDevice(slug: string) {
  return request<Device>(`/api/catalog/devices/${encodeURIComponent(slug)}/`);
}

export function getBrands() {
  return request<Paginated<Brand>>("/api/catalog/brands/?ordering=name");
}
