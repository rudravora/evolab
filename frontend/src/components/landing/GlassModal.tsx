"use client";

// A Liquid Glass sheet (styles: .glass-* in src/app/landing.css). One at a time: Escape or the
// backdrop closes it, Tab stays inside, focus moves in on open and returns to the opener on close.

import * as React from "react";
import { Check, Copy, X } from "lucide-react";

export function GlassModal({
  labelledBy,
  onClose,
  children,
  wide = false,
}: {
  labelledBy: string;
  onClose: () => void;
  children: React.ReactNode;
  wide?: boolean;
}) {
  const ref = React.useRef<HTMLDivElement>(null);
  const close = React.useRef(onClose);
  close.current = onClose;

  React.useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const focusable = () => Array.from(dialog.querySelectorAll<HTMLElement>("button:not([disabled]), a[href], input:not([disabled])"));
    (dialog.querySelector<HTMLElement>("input") ?? focusable()[0])?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        close.current();
        return;
      }
      if (e.key !== "Tab") return;
      const items = focusable();
      const first = items[0];
      const last = items[items.length - 1];
      if (!first || !last) return;
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = overflow;
      previous?.focus();
    };
  }, []);

  return (
    <div
      className="glass-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div ref={ref} className={`glass-card${wide ? " glass-card-wide" : ""}`} role="dialog" aria-modal="true" aria-labelledby={labelledBy}>
        <button type="button" className="glass-close" onClick={onClose} aria-label="Close">
          <X size={18} />
        </button>
        {children}
      </div>
    </div>
  );
}

/** A command with a copy button. Wraps instead of cutting off long commands. */
export function CopyLine({ text }: { text: string }) {
  const [done, setDone] = React.useState(false);
  return (
    <div className="glass-code">
      <code className="mono">{text}</code>
      <button
        type="button"
        aria-label={done ? "Copied" : "Copy command"}
        onClick={async () => {
          try {
            await navigator.clipboard.writeText(text);
            setDone(true);
            window.setTimeout(() => setDone(false), 1600);
          } catch {
            /* clipboard blocked: the text is selectable */
          }
        }}
      >
        {done ? <Check size={15} /> : <Copy size={15} />}
      </button>
    </div>
  );
}

export type OS = "windows" | "unix";

/** Guess the visitor's OS for command examples; they can switch it. */
export function useOS(): [OS, (o: OS) => void] {
  const [os, setOs] = React.useState<OS>("windows");
  React.useEffect(() => {
    if (!/Win/i.test(navigator.userAgent)) setOs("unix");
  }, []);
  return [os, setOs];
}

export function OSSwitch({ os, onChange }: { os: OS; onChange: (o: OS) => void }) {
  return (
    <div className="glass-os" role="radiogroup" aria-label="Your operating system">
      {(
        [
          ["windows", "Windows"],
          ["unix", "macOS / Linux"],
        ] as const
      ).map(([v, label]) => (
        <button key={v} type="button" role="radio" aria-checked={os === v} className={os === v ? "is-on" : ""} onClick={() => onChange(v)}>
          {label}
        </button>
      ))}
    </div>
  );
}
