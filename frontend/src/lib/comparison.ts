import type { Device } from "../types";

/** Highlight a lowest starting price only when every selected offer is
 * numeric, nonnegative and denominated in the *same* currency. Never infer FX. */
export function canCompareStartingPrices(devices: ReadonlyArray<Pick<Device, "lowest_price">>): boolean {
  if (devices.length < 2) return false;
  const prices = devices.map((device) => device.lowest_price);
  const currency = prices[0]?.currency;
  if (!currency) return false;
  return prices.every((price) => {
    if (!price || price.currency !== currency || !price.price.trim()) return false;
    const amount = Number(price.price);
    return Number.isFinite(amount) && amount >= 0;
  });
}
