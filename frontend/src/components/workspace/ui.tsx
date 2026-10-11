"use client";

// v2 primitives in the EvoLab workspace system.
// Shape rule: controls 7px, cards 10px, dialogs and sheets 12px, chips full.
// Colour rule: teal = action and progress, gold = needs a decision, red = real errors,
// slate = evolution and lineage. Minimum text size 12px.

import * as React from "react";
import { cn } from "@/lib/utils";
import { isLive, statusLabel, toneOf, type Tone } from "@/lib/workspace/model";

export const TONE_TEXT: Record<Tone, string> = {
  accent: "text-v2-accent",
  green: "text-v2-green",
  orange: "text-v2-orange",
  red: "text-v2-red",
  purple: "text-v2-purple",
  neutral: "text-v2-text3",
};
const TONE_CHIP: Record<Tone, string> = {
  accent: "bg-v2-accent/[0.08] border-v2-accent/20",
  green: "bg-v2-green/[0.08] border-v2-green/20",
  orange: "bg-v2-gold/[0.12] border-v2-gold/25",
  red: "bg-v2-red/[0.08] border-v2-red/20",
  purple: "bg-v2-purple/[0.09] border-v2-purple/20",
  neutral: "bg-v2-line/[0.04] border-v2-line/[0.1]",
};
export const TONE_FILL: Record<Tone, string> = {
  accent: "bg-v2-accent",
  green: "bg-v2-green",
  orange: "bg-v2-gold",
  red: "bg-v2-red",
  purple: "bg-v2-purple",
  neutral: "bg-v2-text3/40",
};

/** Status chip: the word carries the meaning, colour only reinforces it. */
export function StatusBadge({ status, label, className }: { status: string; label?: string; className?: string }) {
  const tone = toneOf(status);
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 h-6 px-2.5 rounded-full border text-[12px] font-medium whitespace-nowrap",
        TONE_CHIP[tone],
        TONE_TEXT[tone],
        className,
      )}
    >
      {isLive(status) && <span className={cn("w-1.5 h-1.5 rounded-full v2-pulse", TONE_FILL[tone])} aria-hidden />}
      {label ?? statusLabel(status)}
    </span>
  );
}

type ButtonKind = "primary" | "secondary" | "plain" | "destructive" | "ink";
type ButtonSize = "sm" | "md" | "lg";

const KINDS: Record<ButtonKind, string> = {
  primary: "bg-v2-accent text-v2-onaccent hover:brightness-[1.08] hover:shadow-[0_5px_14px_rgb(var(--v2-accent)/0.18)]",
  ink: "bg-v2-text text-v2-bg hover:opacity-90",
  secondary: "bg-v2-surface text-v2-text2 border border-v2-line/[0.12] hover:border-v2-line/25 hover:text-v2-text",
  plain: "text-v2-accent hover:bg-v2-accent/[0.08]",
  destructive: "bg-v2-red/[0.08] text-v2-red border border-v2-red/20 hover:bg-v2-red/[0.13]",
};
const SIZES: Record<ButtonSize, string> = {
  sm: "h-8 px-3 text-[13px] gap-1.5",
  md: "h-9 px-3.5 text-[13px] gap-2",
  lg: "h-11 px-[18px] text-[14px] gap-2",
};

/** Button look, for links that navigate (a link styled as a button, never a button inside a link). */
export function buttonStyles(kind: ButtonKind = "secondary", size: ButtonSize = "md", className?: string) {
  return cn(
    "inline-flex items-center justify-center rounded-[7px] font-semibold whitespace-nowrap transition-[background-color,border-color,box-shadow,filter,transform,opacity] duration-150 hover:-translate-y-px active:translate-y-0 active:scale-[0.99] disabled:opacity-40 disabled:pointer-events-none",
    KINDS[kind],
    SIZES[size],
    className,
  );
}

export const Button = React.forwardRef<
  HTMLButtonElement,
  React.ButtonHTMLAttributes<HTMLButtonElement> & { kind?: ButtonKind; size?: ButtonSize }
>(function Button({ kind = "secondary", size = "md", className, type = "button", ...props }, ref) {
  return <button ref={ref} type={type} className={buttonStyles(kind, size, className)} {...props} />;
});

/** Icon-only button. `label` is required: it is the accessible name and the tooltip. */
export function IconButton({
  label,
  className,
  children,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { label: string }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      className={cn(
        "inline-flex items-center justify-center w-9 h-9 rounded-[7px] text-v2-text3 hover:text-v2-text hover:bg-v2-line/[0.06] transition-colors",
        className,
      )}
      {...props}
    >
      {children}
    </button>
  );
}

export function Card({ className, children, as: As = "section", ...props }: React.HTMLAttributes<HTMLElement> & { as?: "section" | "div" | "article" }) {
  return (
    <As className={cn("v2-card", className)} {...props}>
      {children}
    </As>
  );
}

/** A panel: card with its heading inside, as in the workspace design. */
export function Panel({
  title,
  detail,
  action,
  children,
  className,
  bodyClassName,
  id,
}: {
  title: React.ReactNode;
  detail?: React.ReactNode;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  bodyClassName?: string;
  id?: string;
}) {
  const hid = React.useId();
  return (
    <section className={cn("v2-card min-w-0", className)} aria-labelledby={hid} id={id}>
      <div className="flex items-start justify-between gap-4 px-5 pt-[18px]">
        <div className="min-w-0">
          <h2 id={hid} className="text-[17px] font-semibold text-v2-text leading-tight">
            {title}
          </h2>
          {detail && <p className="text-[13px] text-v2-text3 mt-1">{detail}</p>}
        </div>
        {action && <div className="shrink-0">{action}</div>}
      </div>
      <div className={cn("px-5 pb-4 pt-3", bodyClassName)}>{children}</div>
    </section>
  );
}

/** A titled group with the heading outside the card. */
export function Group({
  title,
  detail,
  action,
  children,
  className,
  id,
}: {
  title: React.ReactNode;
  detail?: React.ReactNode;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  id?: string;
}) {
  const hid = React.useId();
  return (
    <section className={className} aria-labelledby={hid} id={id}>
      <div className="flex items-end justify-between gap-3 mb-3 px-0.5">
        <div className="min-w-0">
          <h2 id={hid} className="text-[17px] font-semibold text-v2-text">
            {title}
          </h2>
          {detail && <p className="text-[13px] text-v2-text3 mt-0.5">{detail}</p>}
        </div>
        {action && <div className="shrink-0">{action}</div>}
      </div>
      {children}
    </section>
  );
}

export function Segmented<T extends string>({
  value,
  options,
  onChange,
  label,
  className,
}: {
  value: T;
  options: { value: T; label: string; badge?: number }[];
  onChange: (v: T) => void;
  label: string;
  className?: string;
}) {
  const refs = React.useRef<(HTMLButtonElement | null)[]>([]);
  const onKey = (e: React.KeyboardEvent, i: number) => {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    e.preventDefault();
    const next = (i + (e.key === "ArrowRight" ? 1 : -1) + options.length) % options.length;
    onChange(options[next].value);
    refs.current[next]?.focus();
  };
  return (
    <div
      role="tablist"
      aria-label={label}
      className={cn(
        "inline-flex p-[3px] rounded-[8px] bg-v2-line/[0.05] border border-v2-line/[0.06] max-w-full overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden",
        className,
      )}
    >
      {options.map((o, i) => {
        const on = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            ref={(el) => {
              refs.current[i] = el;
            }}
            role="tab"
            aria-selected={on}
            tabIndex={on ? 0 : -1}
            onClick={() => onChange(o.value)}
            onKeyDown={(e) => onKey(e, i)}
            className={cn(
              "relative h-8 px-3.5 rounded-[6px] text-[13px] font-medium whitespace-nowrap transition-colors",
              on ? "bg-v2-surface text-v2-text shadow-[0_1px_2px_rgb(var(--v2-line)/0.1)]" : "text-v2-text3 hover:text-v2-text",
            )}
          >
            {o.label}
            {!!o.badge && (
              <span className="ml-1.5 inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 rounded-full bg-v2-orange text-v2-bg text-[11px] font-semibold tnum">
                {o.badge}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

export function FieldLabel({ htmlFor, children, hint }: { htmlFor: string; children: React.ReactNode; hint?: string }) {
  return (
    <label htmlFor={htmlFor} className="block mb-1.5">
      <span className="text-[13px] font-semibold text-v2-text2">{children}</span>
      {hint && <span className="text-[12px] text-v2-text3 ml-1.5 font-normal">{hint}</span>}
    </label>
  );
}

const FIELD =
  "w-full px-3 rounded-[7px] bg-v2-surface text-[14px] text-v2-text placeholder:text-v2-text3/80 border border-v2-line/[0.13] focus:outline-none focus:border-v2-accent focus:ring-[3px] focus:ring-v2-accent/15 transition-[border-color,box-shadow]";

export const TextField = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(function TextField(
  { className, ...props },
  ref,
) {
  return <input ref={ref} {...props} className={cn(FIELD, "h-10", className)} />;
});

export const TextArea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(function TextArea(
  { className, ...props },
  ref,
) {
  return <textarea ref={ref} {...props} className={cn(FIELD, "py-2.5 resize-y leading-relaxed", className)} />;
});

export function Skeleton({ className }: { className?: string }) {
  // A span, so it can sit inside text elements such as <p> without breaking hydration.
  return <span className={cn("block v2-skeleton", className)} aria-hidden />;
}

export function Empty({
  icon,
  title,
  children,
  action,
  className,
}: {
  icon?: React.ReactNode;
  title: string;
  children?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center text-center px-6 py-10", className)}>
      {icon && <div className="text-v2-text3 mb-3">{icon}</div>}
      <div className="text-[15px] font-semibold text-v2-text">{title}</div>
      {children && <p className="text-[13px] text-v2-text3 mt-1 max-w-[44ch] leading-relaxed">{children}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function Notice({
  tone = "neutral",
  icon,
  children,
  action,
  className,
}: {
  tone?: Tone;
  icon?: React.ReactNode;
  children: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div role="status" className={cn("flex items-start gap-3 rounded-[10px] border px-4 py-3 text-[14px]", TONE_CHIP[tone], className)}>
      {icon && <span className={cn("mt-0.5 shrink-0", TONE_TEXT[tone])}>{icon}</span>}
      <div className="flex-1 min-w-0 text-v2-text">{children}</div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}

/** Thin determinate meter (budget, CPU). Gold past 80%, red past 100%. */
export function Meter({ value, label, className }: { value: number | null; label: string; className?: string }) {
  const v = value ?? 0;
  const tone: Tone = v >= 1 ? "red" : v >= 0.8 ? "orange" : "accent";
  return (
    <div
      role="meter"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(v * 100)}
      className={cn("h-1 rounded-full bg-v2-line/[0.08] overflow-hidden", className)}
    >
      <div className={cn("h-full rounded-full transition-[width] duration-500", TONE_FILL[tone])} style={{ width: `${Math.max(2, Math.min(1, v) * 100)}%` }} />
    </div>
  );
}

export function Pre({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <pre
      className={cn(
        "v2-mono text-[12px] leading-relaxed text-v2-text2 bg-v2-raised rounded-[7px] p-3 overflow-auto max-h-80 whitespace-pre-wrap break-words v2-scroll",
        className,
      )}
    >
      {children}
    </pre>
  );
}

export function json(value: unknown, max = 4000) {
  const text = typeof value === "string" ? value : JSON.stringify(value, null, 2);
  return text && text.length > max ? `${text.slice(0, max)}\n... (truncated)` : text;
}
