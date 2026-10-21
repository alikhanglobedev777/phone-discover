import type { Device } from "../types";

/** Show only released, available phones with documented dates. Never use
 * undated catalog entries or future-dated announcements as "latest". */
export function selectLatestPhones(
  phones: Device[],
  limit = 4,
  today = new Date(),
): Device[] {
  const todayIso = [
    today.getFullYear(),
    String(today.getMonth() + 1).padStart(2, "0"),
    String(today.getDate()).padStart(2, "0"),
  ].join("-");
  const seen = new Set<string>();
  return [...phones]
    .filter((device) =>
      device.status === "available" &&
      typeof device.release_date === "string" &&
      /^\d{4}-\d{2}-\d{2}$/.test(device.release_date) &&
      device.release_date <= todayIso)
    .sort((a, b) => (b.release_date ?? "").localeCompare(a.release_date ?? ""))
    .filter((device) => {
      if (seen.has(device.slug)) return false;
      seen.add(device.slug);
      return true;
    })
    .slice(0, limit);
}
