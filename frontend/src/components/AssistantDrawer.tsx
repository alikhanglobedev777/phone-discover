import { useEffect, useRef, useState } from "react";
import { RecommendationAssistant } from "./RecommendationAssistant";
import type { MarketSearchFilters } from "../lib/pakistan";

type Props = {
  onOpenDevice: (slug: string) => void;
  onCompareDevice: (slug: string) => void;
  marketResearchRequest?: { id: number; filters: MarketSearchFilters } | null;
};

export function AssistantDrawer({ onOpenDevice, onCompareDevice, marketResearchRequest }: Props) {
  const [open, setOpen] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [hasOpened, setHasOpened] = useState(false);
  const launcherRef = useRef<HTMLButtonElement>(null);
  const drawerRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  function openDrawer() { setHasOpened(true); setOpen(true); }
  useEffect(() => {
    if (marketResearchRequest) openDrawer();
  }, [marketResearchRequest]);
  function closeDrawer() { setOpen(false); setExpanded(false); }

  useEffect(() => {
    if (!open) return;
    const wasLocked = document.body.classList.contains("modal-open");
    document.body.classList.add("modal-open");
    closeRef.current?.focus();

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        closeDrawer();
        return;
      }
      if (event.key !== "Tab" || !drawerRef.current) return;
      const dialog = drawerRef.current;
      const focusable = [...dialog.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), summary, [tabindex]:not([tabindex="-1"])',
      )].filter((element) => element.getClientRects().length > 0 && element.tabIndex >= 0);
      if (!focusable.length) { event.preventDefault(); dialog.focus(); return; }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && (document.activeElement === first || document.activeElement === dialog)) {
        event.preventDefault(); last.focus();
      } else if (!event.shiftKey && (document.activeElement === last || !dialog.contains(document.activeElement))) {
        event.preventDefault(); first.focus();
      }
    }

    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      if (!wasLocked) document.body.classList.remove("modal-open");
      launcherRef.current?.focus();
    };
  }, [open]);

  return (
    <div className={`chat-dock ${open ? "chat-dock-open" : ""}`}>
      <button
        type="button"
        className="chat-launcher"
        ref={launcherRef}
        aria-label="Open Phone Discover assistant"
        aria-expanded={open}
        aria-controls="phone-assistant-panel"
        onClick={openDrawer}
      >
        <span className="chat-launcher-icon" aria-hidden="true">✦</span>
        <span>Ask phone assistant</span>
        <span className="chat-launcher-arrow" aria-hidden="true">↗</span>
      </button>
      {open && <div className="chat-scrim" aria-hidden="true" onClick={closeDrawer} />}
      {hasOpened && (
        <div
          className={`chat-drawer ${open ? "is-open" : ""} ${expanded ? "is-expanded" : ""}`}
          id="phone-assistant-panel"
          role="dialog"
          aria-modal="true"
          aria-label={expanded ? "Phone Discover assistant full screen" : "Phone Discover assistant"}
          aria-hidden={!open}
          inert={!open}
          hidden={!open}
          tabIndex={-1}
          ref={drawerRef}
        >
          <div className="chat-drawer-topbar">
            <span><span aria-hidden="true">✦</span> Phone Discover</span>
            <div className="chat-drawer-actions">
              <button
                type="button"
                className="chat-resize-button"
                onClick={() => setExpanded((current) => !current)}
                aria-label={expanded ? "Minimize phone assistant" : "Expand phone assistant to full screen"}
                aria-pressed={expanded}
                title={expanded ? "Back to mini chat" : "Expand to full screen"}
              >
                {expanded ? "Minimize ↙" : "Expand ⤢"}
              </button>
              <button type="button" ref={closeRef} onClick={closeDrawer} aria-label="Close phone assistant">Close <span aria-hidden="true">×</span></button>
            </div>
          </div>
          <RecommendationAssistant
            marketResearchRequest={marketResearchRequest}
            onOpenDevice={(slug) => { closeDrawer(); onOpenDevice(slug); }}
            onCompareDevice={(slug) => { onCompareDevice(slug); closeDrawer(); }}
          />
        </div>
      )}
    </div>
  );
}
