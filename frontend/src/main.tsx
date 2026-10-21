import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
// Bundle the styles with the React entrypoint instead of relying on a
// separately requested, hashed CSS asset. This makes the complete layout
// available even when a CDN/browser serves stale HTML or blocks CSS requests.
// Keep the cascade in the same order as the previous stylesheet imports.
import baseStyles from "./styles.css?inline";
import designStyles from "./design-system.css?inline";
import brandStyles from "./brand-refresh.css?inline";
import detailStyles from "./detail-modal.css?inline";
import galleryStyles from "./device-gallery.css?inline";
import compareStyles from "./compare-page.css?inline";
import homeStyles from "./home-enhancements.css?inline";

const siteStyles = document.createElement("style");
siteStyles.setAttribute("data-phone-discover-styles", "bundled");
siteStyles.textContent = [
  baseStyles,
  designStyles,
  brandStyles,
  detailStyles,
  galleryStyles,
  compareStyles,
  homeStyles,
].join("\n");
document.head.appendChild(siteStyles);

const queryClient = new QueryClient();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
);
