import type { Device, DeviceImage } from "../types";

export type GalleryPhoto = {
  key: string;
  url: string;
  alt: string;
  view: "front" | "back" | "side" | "detail" | "unspecified";
  color: number | null;
};

const viewLabels: Record<GalleryPhoto["view"], string> = {
  front: "Front", back: "Back", side: "Side", detail: "Detail", unspecified: "Photo",
};

export function viewLabel(view: GalleryPhoto["view"]) {
  return viewLabels[view];
}

/** Only real, catalog-provided URLs. Never duplicate a photo to manufacture new angles. */
export function galleryPhotos(device: Pick<Device, "brand" | "name" | "primary_image_url" | "images">): GalleryPhoto[] {
  const photos: GalleryPhoto[] = [];
  const seen = new Set<string>();
  const add = (url: string | undefined, image?: DeviceImage) => {
    const normalized = url?.trim();
    if (!normalized || seen.has(normalized)) return;
    seen.add(normalized);
    const view = image?.view || "unspecified";
    photos.push({
      key: String(image?.id ?? `primary-${normalized}`),
      url: normalized,
      alt: image?.alt_text?.trim() || `${device.brand.name} ${device.name} ${viewLabel(view).toLowerCase()}`,
      view,
      color: image?.color ?? null,
    });
  };
  const images = [...(device.images ?? [])].sort((a, b) =>
    Number(b.is_primary) - Number(a.is_primary) || a.sort_order - b.sort_order || a.id - b.id,
  );
  // Prefer catalog metadata when the primary URL is also a gallery image.
  const primary = images.find((photo) => photo.image_url === device.primary_image_url);
  add(device.primary_image_url, primary);
  images.forEach((image) => add(image.image_url, image));
  return photos;
}

export function photosForColor(photos: GalleryPhoto[], selectedColor: number | null) {
  if (selectedColor === null) return { photos, isRepresentative: false };
  const matching = photos.filter((photo) => photo.color === selectedColor);
  if (matching.length) return { photos: matching, isRepresentative: false };
  const generic = photos.filter((photo) => photo.color === null);
  return { photos: generic, isRepresentative: true };
}
