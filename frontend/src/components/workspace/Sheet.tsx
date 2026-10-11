"use client";

// Modal surfaces: a side sheet for detail views (task, job) and a centred dialog (new research).
// One at a time. Esc or the backdrop closes them, Tab stays inside, focus moves in on open and
// returns to the opener on close.

import * as React from "react";
import { X } from "@phosphor-icons/react";
import { IconButton } from "./ui";

/** Focus trap, Esc to close, scroll lock. Runs once per open: onClose is read through a ref, so
 *  parents re-rendering (polling) never steal focus back. */
function useModal(panel: React.RefObject<HTMLElement | null>, onClose: () => void) {
  const close = React.useRef(onClose);
  close.current = onClose;
  React.useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    const first = panel.current?.querySelector<HTMLElement>("[data-autofocus]");
    (first ?? panel.current)?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close.current();
      if (e.key === "Tab" && panel.current) {
        const items = panel.current.querySelectorAll<HTMLElement>('a[href],button:not([disabled]),input:not([disabled]),textarea:not([disabled]),select,[tabindex="0"]');
        if (!items.length) return;
        const a = items[0];
        const b = items[items.length - 1];
        if (e.shiftKey && document.activeElement === a) {
          e.preventDefault();
          b.focus();
        } else if (!e.shiftKey && document.activeElement === b) {
          e.preventDefault();
          a.focus();
        }
      }
    };
    document.addEventListener("keydown", onKey);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = overflow;
      opener?.focus?.();
    };
  }, [panel]);
}

export function Sheet({
  title,
  subtitle,
  onClose,
  children,
  wide,
}: {
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  onClose: () => void;
  children: React.ReactNode;
  wide?: boolean;
}) {
  const panel = React.useRef<HTMLDivElement>(null);
  const titleId = React.useId();
  useModal(panel, onClose);

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-[rgb(22_37_31/0.42)] backdrop-blur-[3px] v2-fade" onClick={onClose} aria-hidden />
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className={`v2-sheet relative h-full w-full ${wide ? "max-w-3xl" : "max-w-2xl"} bg-v2-bg sm:rounded-l-[12px] shadow-[var(--v2-shadow-lg)] flex flex-col outline-none`}
      >
        <div className="flex items-start justify-between gap-3 px-6 pt-5 pb-4 border-b border-v2-line/[0.08]">
          <div className="min-w-0">
            <h2 id={titleId} className="text-[22px] font-semibold text-v2-text">
              {title}
            </h2>
            {subtitle && <div className="mt-1.5">{subtitle}</div>}
          </div>
          <IconButton label="Close" onClick={onClose}>
            <X size={18} />
          </IconButton>
        </div>
        <div className="flex-1 overflow-y-auto v2-scroll px-6 py-5 space-y-6">{children}</div>
      </div>
    </div>
  );
}

export function Dialog({
  title,
  intro,
  onClose,
  children,
}: {
  title: React.ReactNode;
  intro?: React.ReactNode;
  onClose: () => void;
  children: React.ReactNode;
}) {
  const panel = React.useRef<HTMLDivElement>(null);
  const titleId = React.useId();
  useModal(panel, onClose);
  return (
    <div className="fixed inset-0 z-50 grid place-items-center overflow-y-auto p-4 sm:p-6">
      <div className="fixed inset-0 bg-[rgb(22_37_31/0.55)] backdrop-blur-[4px] v2-fade" onClick={onClose} aria-hidden />
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className="v2-pop relative w-full max-w-[560px] max-h-[calc(100dvh-32px)] overflow-y-auto v2-scroll rounded-[12px] border border-v2-line/[0.1] bg-v2-surface shadow-[var(--v2-shadow-lg)] p-6 outline-none"
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 id={titleId} className="text-[26px] font-semibold leading-tight text-v2-text">
              {title}
            </h2>
            {intro && <p className="text-[14px] text-v2-text3 mt-1.5">{intro}</p>}
          </div>
          <IconButton label="Close" onClick={onClose} className="-mr-2 -mt-1">
            <X size={18} />
          </IconButton>
        </div>
        <div className="mt-5">{children}</div>
      </div>
    </div>
  );
}
