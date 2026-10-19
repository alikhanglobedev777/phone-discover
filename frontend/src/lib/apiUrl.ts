/**
 * Prefix API paths with the Django origin when frontend and backend are hosted
 * on separate domains. Empty in local development (Vite proxies /api).
 * VITE_API_BASE_URL is a PUBLIC build-time variable, never put keys here.
 */
export function apiUrl(path: string): string {
  const backendOrigin = (import.meta.env?.VITE_API_BASE_URL ?? "").trim().replace(/\/+$/, "");
  return `${backendOrigin}${path}`;
}
