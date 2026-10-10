import Link from "next/link";
import { ArrowLeft, Play, Cpu, ShieldCheck } from "lucide-react";

export default function DashboardPage() {
  return (
    <main className="min-h-screen bg-canvas text-foreground p-6 sm:p-12 flex flex-col justify-between">
      <div className="max-w-4xl mx-auto w-full">
        <div className="flex items-center justify-between pb-6 border-b border-border-subtle mb-10">
          <div className="flex items-center gap-3">
            <Link
              href="/"
              className="inline-flex items-center gap-2 text-xs font-mono text-foreground-muted hover:text-foreground transition-colors px-3 py-1.5 rounded-btn bg-canvas-elevated border border-border-subtle"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              <span>Back to Landing</span>
            </Link>
            <span className="font-mono text-xs text-foreground-faint">/</span>
            <span className="font-mono text-xs text-cyan-highlight">Dashboard</span>
          </div>

          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-cyan shadow-[0_0_8px_rgba(56,189,248,0.8)]" />
            <span className="font-mono text-xs text-foreground-secondary">Worker Standby</span>
          </div>
        </div>

        <div className="p-8 sm:p-12 rounded-panel bg-card/80 border border-border-medium shadow-card-depth text-center flex flex-col items-center">
          <div className="w-12 h-12 rounded-card bg-canvas-elevated border border-cyan/40 shadow-glow-cyan flex items-center justify-center mb-5">
            <Cpu className="w-6 h-6 text-cyan-highlight" />
          </div>

          <h1 className="text-3xl sm:text-4xl font-semibold tracking-tight text-foreground mb-3">
            EvoLab Research Dashboard
          </h1>

          <p className="text-base text-foreground-secondary max-w-lg leading-relaxed mb-8">
            Your personal research workspace. Connect your laptop to start an investigation and track real-time progress.
          </p>

          <div className="p-4 rounded-card bg-canvas-elevated border border-border-subtle font-mono text-xs text-foreground-muted max-w-md w-full mb-8 flex items-center justify-between">
            <span>Status: Ready for input</span>
            <span className="text-cyan-highlight">Local session</span>
          </div>

          <Link
            href="/"
            className="inline-flex items-center justify-center h-10 px-6 rounded-btn bg-cyan text-canvas font-semibold text-sm hover:bg-cyan-highlight transition-all shadow-glow-cyan"
          >
            Return to Overview
          </Link>
        </div>
      </div>

      <footer className="max-w-4xl mx-auto w-full pt-8 text-center font-mono text-xs text-foreground-faint">
        EvoLab | Autonomous Research Environment
      </footer>
    </main>
  );
}
