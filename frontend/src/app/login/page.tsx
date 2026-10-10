"use client";

import * as React from "react";
import Link from "next/link";
import { ArrowLeft, ArrowRight, Lock } from "lucide-react";
import { api, ApiError } from "@/lib/api";

// One owner account (D-044): the backend checks a single password and sets an HttpOnly session cookie.
export default function LoginPage() {
  const [password, setPassword] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api("/auth/login", "POST", { password });
      const next = new URLSearchParams(window.location.search).get("next");
      window.location.href = next && next.startsWith("/") ? next : "/dashboard";
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Cannot reach the backend. Is it running?");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="min-h-screen bg-canvas text-foreground flex flex-col justify-between p-6 sm:p-10">
      <div className="max-w-md mx-auto w-full flex items-center justify-between">
        <Link
          href="/"
          className="inline-flex items-center gap-2 text-xs font-mono text-foreground-muted hover:text-foreground transition-colors px-3 py-1.5 rounded-btn bg-canvas-elevated border border-border-subtle"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          <span>Back to Landing</span>
        </Link>
        <Link href="/" className="flex items-center gap-2.5">
          <div className="w-6 h-6 rounded-btn bg-canvas-elevated border border-border-medium flex items-center justify-center">
            <span className="w-2 h-2 rounded-full bg-cyan shadow-[0_0_6px_rgba(56,189,248,0.8)]" />
          </div>
          <span className="font-semibold text-foreground text-sm tracking-tight">EvoLab</span>
        </Link>
      </div>

      <div className="max-w-md mx-auto w-full my-auto py-8">
        <div className="p-7 sm:p-9 rounded-panel bg-card/85 backdrop-blur-xl border border-border-subtle shadow-card-depth">
          <div className="mb-8">
            <span className="font-mono text-[10px] uppercase tracking-wider text-cyan-highlight block mb-1">Researcher Portal</span>
            <h1 className="text-2xl font-semibold tracking-tight text-foreground mb-1.5">Sign in to EvoLab</h1>
            <p className="text-xs sm:text-sm text-foreground-muted leading-relaxed">
              Enter the owner password to launch and supervise research runs.
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-mono uppercase tracking-wider text-foreground-secondary mb-1.5">Password</label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-foreground-faint">
                  <Lock className="w-4 h-4" />
                </div>
                <input
                  type="password"
                  required
                  autoFocus
                  placeholder="Owner password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full h-10 pl-9 pr-3 rounded-btn bg-canvas-elevated border border-border-subtle text-foreground text-sm placeholder:text-foreground-faint focus:outline-none focus:border-cyan/50 focus:ring-1 focus:ring-cyan/50 transition-all font-mono"
                />
              </div>
            </div>
            {error && <div className="text-xs text-red-300 bg-red-500/10 border border-red-500/25 rounded-btn p-2.5">{error}</div>}
            <button
              type="submit"
              disabled={busy}
              className="w-full h-10 mt-2 rounded-btn font-semibold text-xs tracking-wide uppercase bg-cyan text-canvas hover:bg-cyan-highlight transition-all shadow-glow-cyan flex items-center justify-center gap-2 disabled:opacity-60"
            >
              <span>{busy ? "Signing in" : "Sign In"}</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </form>
        </div>
      </div>

      <div className="max-w-md mx-auto w-full text-center font-mono text-[11px] text-foreground-faint">
        EvoLab - Autonomous Research Environment
      </div>
    </main>
  );
}
