import Link from "next/link";

// The EvoLab mark and wordmark, as in the EvoLab UI prototype (classes from src/app/landing.css).
export default function EvoMark({ compact = false, light = false, to = "/" }: { compact?: boolean; light?: boolean; to?: string }) {
  return (
    <Link href={to} className={`brand-lockup${compact ? " brand-lockup-compact" : ""}${light ? " brand-lockup-light" : ""}`} aria-label="EvoLab home">
      <svg className="brand-symbol" viewBox="0 0 36 36" fill="none" aria-hidden="true">
        <path
          d="M10.25 11.5c1.7-3.1 4.15-4.65 7.45-4.65 4.42 0 7.05 3.08 7.05 6.8 0 4.05-2.18 6.17-6.95 6.17h-2.3c-3.06 0-5.42 1.77-5.42 4.8 0 2.7 2.02 4.53 4.92 4.53 4.22 0 7.2-2.86 8.91-8.6"
          stroke="currentColor"
          strokeWidth="1.55"
          strokeLinecap="round"
        />
        <path d="M8.25 16.15h6.15M21.25 11.65h6.5" stroke="currentColor" strokeWidth="1.45" strokeLinecap="round" />
        <circle cx="8.1" cy="16.15" r="2.05" fill="#147A69" />
        <circle cx="28.12" cy="11.65" r="2.05" fill="#B77937" />
        <circle cx="15.02" cy="28.8" r="2.05" fill="#147A69" />
        <circle cx="18.1" cy="18.15" r="1.6" fill="currentColor" />
      </svg>
      {!compact && (
        <span className="brand-word">
          Evo<span>Lab</span>
        </span>
      )}
    </Link>
  );
}
