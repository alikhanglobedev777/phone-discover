import { useEffect, useRef } from "react";

/** Keep keyboard navigation inside a dialog, restore focus after closing,
 * and prevent page scrolling without interfering with an existing overlay. */
export function useModalKeyboard<T extends HTMLElement>(onClose: () => void) {
  const dialogRef = useRef<T | null>(null);
  const closeRef = useRef(onClose);

  useEffect(() => { closeRef.current = onClose; }, [onClose]);

  useEffect(() => {
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const wasLocked = document.body.classList.contains("modal-open");
    const dialog = dialogRef.current;
    document.body.classList.add("modal-open");
    dialog?.focus();

    function handleKeydown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        closeRef.current();
        return;
      }
      if (event.key !== "Tab" || !dialog) return;
      const candidates = [...dialog.querySelectorAll<HTMLElement>(
        'a[href], button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])',
      )].filter((element) => element.getClientRects().length > 0 && element.tabIndex >= 0);
      if (!candidates.length) {
        event.preventDefault();
        dialog.focus();
        return;
      }
      const first = candidates[0];
      const last = candidates[candidates.length - 1];
      const focused = document.activeElement;
      if (event.shiftKey && (focused === first || focused === dialog)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (focused === last || !dialog.contains(focused))) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", handleKeydown);
    return () => {
      document.removeEventListener("keydown", handleKeydown);
      if (!wasLocked) document.body.classList.remove("modal-open");
      previousFocus?.focus();
    };
  }, []);

  return dialogRef;
}
