"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

const STATUS_STYLE: Record<string, string> = {
  done: "bg-emerald-500/10 text-emerald-300 border-emerald-500/25",
  expanded: "bg-emerald-500/10 text-emerald-300 border-emerald-500/25",
  approved: "bg-emerald-500/10 text-emerald-300 border-emerald-500/25",
  online: "bg-emerald-500/10 text-emerald-300 border-emerald-500/25",
  active: "bg-emerald-500/10 text-emerald-300 border-emerald-500/25",
  running: "bg-cyan/10 text-cyan-highlight border-cyan/30",
  claimed: "bg-cyan/10 text-cyan-highlight border-cyan/30",
  queued: "bg-cyan/5 text-cyan-highlight/80 border-cyan/20",
  waiting_for_job: "bg-cyan/5 text-cyan-highlight/80 border-cyan/20",
  planning: "bg-cyan/5 text-cyan-highlight/80 border-cyan/20",
  pending: "bg-amber/10 text-amber-highlight border-amber/30",
  awaiting_approval: "bg-amber/10 text-amber-highlight border-amber/30",
  waiting_for_approval: "bg-amber/10 text-amber-highlight border-amber/30",
  proposed: "bg-amber/5 text-amber-highlight/80 border-amber/20",
  paused: "bg-amber/5 text-amber-highlight/80 border-amber/20",
  failed: "bg-red-500/10 text-red-300 border-red-500/25",
  rejected: "bg-red-500/10 text-red-300 border-red-500/25",
  expired: "bg-red-500/10 text-red-300 border-red-500/25",
  timed_out: "bg-red-500/10 text-red-300 border-red-500/25",
  pruned: "bg-white/[0.04] text-foreground-muted border-border-subtle",
  killed: "bg-white/[0.04] text-foreground-muted border-border-subtle",
  cancelled: "bg-white/[0.04] text-foreground-muted border-border-subtle",
  skipped: "bg-white/[0.04] text-foreground-muted border-border-subtle",
  blocked: "bg-white/[0.03] text-foreground-faint border-border-subtle",
  offline: "bg-white/[0.03] text-foreground-faint border-border-subtle",
  retired: "bg-white/[0.03] text-foreground-faint border-border-subtle",
};

export function Status({ value, className }: { value: string; className?: string }) {
  const live = ["running", "claimed", "planning"].includes(value);
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border text-[10px] font-mono uppercase tracking-wider whitespace-nowrap",
        STATUS_STYLE[value] ?? "bg-white/[0.04] text-foreground-secondary border-border-subtle",
        className,
      )}
    >
      {live && <span className="w-1.5 h-1.5 rounded-full bg-cyan animate-pulse" />}
      {value.replaceAll("_", " ")}
    </span>
  );
}

export function Panel({
  title,
  action,
  children,
  className,
  glow,
}: {
  title?: React.ReactNode;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  glow?: "cyan" | "amber";
}) {
  return (
    <section
      className={cn(
        "rounded-card bg-card/85 backdrop-blur-md border border-border-subtle shadow-inner-bevel",
        glow === "cyan" && "border-cyan/30 shadow-glow-cyan",
        glow === "amber" && "border-amber/40 shadow-glow-amber",
        className,
      )}
    >
      {(title || action) && (
        <div className="flex items-center justify-between gap-3 px-4 pt-3.5 pb-2">
          <h2 className="font-mono text-[11px] uppercase tracking-[0.18em] text-foreground-secondary">{title}</h2>
          {action}
        </div>
      )}
      <div className="px-4 pb-4">{children}</div>
    </section>
  );
}

export function Label({ children }: { children: React.ReactNode }) {
  return <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-foreground-faint mb-1">{children}</div>;
}

export function Btn({
  variant = "secondary",
  className,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "cyan" | "secondary" | "danger" | "ghost" }) {
  const styles = {
    cyan: "bg-cyan text-canvas font-semibold hover:bg-cyan-highlight shadow-glow-cyan border border-cyan-highlight/30",
    secondary: "bg-canvas-elevated text-foreground border border-border-subtle hover:border-cyan/40",
    danger: "bg-red-500/10 text-red-300 border border-red-500/30 hover:bg-red-500/20",
    ghost: "text-foreground-muted hover:text-foreground hover:bg-white/[0.05]",
  };
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center gap-1.5 h-8 px-3 rounded-btn text-xs font-medium transition-all active:scale-[0.98] disabled:opacity-50 disabled:pointer-events-none",
        styles[variant],
        className,
      )}
      {...props}
    />
  );
}

export function Field(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={cn(
        "w-full h-9 px-3 rounded-btn bg-canvas-elevated border border-border-subtle text-sm text-foreground placeholder:text-foreground-faint focus:outline-none focus:border-cyan/50",
        props.className,
      )}
    />
  );
}

export function Json({ value, max = 4000 }: { value: unknown; max?: number }) {
  const text = typeof value === "string" ? value : JSON.stringify(value, null, 2);
  return (
    <pre className="text-[11px] leading-relaxed font-mono text-foreground-secondary bg-canvas-subtle border border-border-subtle rounded-btn p-2.5 overflow-auto max-h-80 whitespace-pre-wrap break-words">
      {text && text.length > max ? text.slice(0, max) + "\n... (truncated)" : text}
    </pre>
  );
}

export function Empty({ children }: { children: React.ReactNode }) {
  return <div className="text-xs text-foreground-faint py-4 text-center">{children}</div>;
}

export function short(id?: string | null) {
  return id ? id.replace(/^agt_/, "").replaceAll("_", " ") : "";
}
