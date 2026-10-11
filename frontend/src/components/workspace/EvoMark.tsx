import Link from "next/link";
import { cn } from "@/lib/utils";

// The EvoLab mark: three linked orbital points around a central node, with the spaced wordmark.
export function EvoMark({ compact = false, href = "/dashboard", className }: { compact?: boolean; href?: string; className?: string }) {
  return (
    <Link href={href} aria-label="EvoLab home" className={cn("inline-flex items-center gap-2 text-v2-text w-max", className)}>
      <svg viewBox="0 0 36 36" fill="none" aria-hidden className={compact ? "w-7 h-7" : "w-8 h-8"}>
        <path
          d="M10.25 11.5c1.7-3.1 4.15-4.65 7.45-4.65 4.42 0 7.05 3.08 7.05 6.8 0 4.05-2.18 6.17-6.95 6.17h-2.3c-3.06 0-5.42 1.77-5.42 4.8 0 2.7 2.02 4.53 4.92 4.53 4.22 0 7.2-2.86 8.91-8.6"
          stroke="currentColor"
          strokeWidth="1.55"
          strokeLinecap="round"
        />
        <path d="M8.25 16.15h6.15M21.25 11.65h6.5" stroke="currentColor" strokeWidth="1.45" strokeLinecap="round" />
        <circle cx="8.1" cy="16.15" r="2.05" fill="rgb(var(--v2-accent))" />
        <circle cx="28.12" cy="11.65" r="2.05" fill="rgb(var(--v2-gold))" />
        <circle cx="15.02" cy="28.8" r="2.05" fill="rgb(var(--v2-accent))" />
        <circle cx="18.1" cy="18.15" r="1.6" fill="currentColor" />
      </svg>
      {!compact && (
        <span className="text-[20px] leading-none font-semibold tracking-[-0.055em]">
          Evo<span className="text-v2-accent">Lab</span>
        </span>
      )}
    </Link>
  );
}
