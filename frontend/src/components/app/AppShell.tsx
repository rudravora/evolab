"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Bot, Brain, LayoutDashboard, LogOut } from "lucide-react";
import { api } from "@/lib/api";
import { usePoll } from "@/lib/hooks";
import type { Health } from "@/lib/types";
import { cn } from "@/lib/utils";

const LINKS = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/agents", label: "Agents", icon: Bot },
  { href: "/memory", label: "Memory", icon: Brain },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { data: health, error } = usePoll<Health>("/health", 60000);

  React.useEffect(() => {
    // Any dashboard route needs a session; /auth/me redirects to /login on 401 (see lib/api).
    api("/auth/me").catch(() => undefined);
  }, []);

  const signOut = async () => {
    await api("/auth/logout", "POST").catch(() => undefined);
    router.push("/login");
  };

  return (
    <div className="min-h-screen bg-canvas text-foreground">
      {health?.mode === "simulated" && (
        <div className="bg-amber/15 border-b border-amber/30 text-amber-highlight text-center text-xs font-mono py-1.5 tracking-wide">
          SIMULATED MODE: scripted AI replies and a simulated laptop worker. The pipeline code is real.
        </div>
      )}
      {error && (
        <div className="bg-red-500/10 border-b border-red-500/30 text-red-300 text-center text-xs font-mono py-1.5">
          Backend unreachable. Start it with: py -m uvicorn app.main:app --port 8000 (inside backend/)
        </div>
      )}
      <header className="sticky top-0 z-40 h-14 bg-canvas/85 backdrop-blur-xl border-b border-border-subtle">
        <div className="max-w-[1400px] mx-auto h-full px-4 sm:px-6 flex items-center justify-between gap-4">
          <Link href="/dashboard" className="flex items-center gap-2.5 shrink-0">
            <div className="w-7 h-7 rounded-btn bg-canvas-elevated border border-border-medium flex items-center justify-center">
              <span className="w-2.5 h-2.5 rounded-full bg-cyan shadow-[0_0_8px_rgba(56,189,248,0.8)]" />
            </div>
            <span className="font-semibold tracking-tight">EvoLab</span>
          </Link>
          <nav className="flex items-center gap-1 overflow-x-auto">
            {LINKS.map(({ href, label, icon: Icon }) => (
              <Link
                key={href}
                href={href}
                className={cn(
                  "inline-flex items-center gap-1.5 h-8 px-3 rounded-btn text-xs font-medium transition-colors",
                  pathname?.startsWith(href) || (href === "/dashboard" && pathname?.startsWith("/runs"))
                    ? "bg-canvas-elevated text-foreground border border-border-medium"
                    : "text-foreground-muted hover:text-foreground hover:bg-white/[0.04]",
                )}
              >
                <Icon className="w-3.5 h-3.5" />
                <span className="hidden sm:inline">{label}</span>
              </Link>
            ))}
          </nav>
          <div className="flex items-center gap-3 shrink-0">
            <span className="hidden md:inline font-mono text-[10px] uppercase tracking-[0.18em] text-foreground-faint">
              {health ? `${health.mode} v${health.version}` : "connecting"}
            </span>
            <button
              onClick={signOut}
              className="inline-flex items-center gap-1.5 h-8 px-3 rounded-btn text-xs text-foreground-muted hover:text-foreground hover:bg-white/[0.04]"
            >
              <LogOut className="w-3.5 h-3.5" /> <span className="hidden sm:inline">Sign out</span>
            </button>
          </div>
        </div>
      </header>
      <main className="max-w-[1400px] mx-auto px-4 sm:px-6 py-6">{children}</main>
    </div>
  );
}
