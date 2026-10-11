"use client";

// v2 workspace frame: navigation rail on wide screens, top bar plus tab bar on narrow ones.
// Appearance follows the system setting through CSS (src/app/(workspace)/workspace.css). Also owns the
// workspace-level data every page needs, so the pages do not poll the same endpoints twice.

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Books, Laptop, SignOut, SquaresFour, UsersThree, WarningCircle } from "@phosphor-icons/react";
import { api } from "@/lib/api";
import { usePoll } from "@/lib/hooks";
import type { Approval, Health, Project, Worker } from "@/lib/types";
import { cn } from "@/lib/utils";
import { ago, statusLabel, toneOf } from "@/lib/workspace/model";
import { EvoMark } from "./EvoMark";
import { TONE_FILL } from "./ui";

interface Workspace {
  health?: Health;
  backendDown: boolean;
  projects?: Project[];
  workers?: Worker[];
  approvals?: Approval[];
  reloadProjects: () => void;
  reloadWorkers: () => void;
  reloadApprovals: () => void;
}

const WorkspaceContext = React.createContext<Workspace | null>(null);

export function useWorkspace() {
  const ctx = React.useContext(WorkspaceContext);
  if (!ctx) throw new Error("useWorkspace must be used inside the v2 Shell");
  return ctx;
}

const NAV = [
  { href: "/dashboard", label: "Overview", icon: SquaresFour, match: (p: string) => p === "/dashboard" || p.startsWith("/runs") },
  { href: "/agents", label: "Agent team", icon: UsersThree, match: (p: string) => p.startsWith("/agents") },
  { href: "/memory", label: "Memory", icon: Books, match: (p: string) => p.startsWith("/memory") },
];

function crumb(pathname: string) {
  if (pathname.startsWith("/runs")) return "Run";
  if (pathname.startsWith("/agents")) return "Agent team";
  if (pathname.startsWith("/memory")) return "Memory";
  return "Overview";
}

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname() ?? "/dashboard";

  const { data: health, error: healthError } = usePoll<Health>("/health", 30000);
  const { data: projects, reload: reloadProjects } = usePoll<Project[]>("/projects", 15000);
  const { data: workers, reload: reloadWorkers } = usePoll<Worker[]>("/workers", 15000);
  const { data: approvals, reload: reloadApprovals } = usePoll<Approval[]>("/approvals?status=pending", 15000);

  React.useEffect(() => {
    // Every v2 page needs a session; on 401 lib/api sends the browser to /login?next=<this page>.
    api("/auth/me").catch(() => undefined);
  }, []);

  const signOut = async () => {
    await api("/auth/logout", "POST").catch(() => undefined);
    window.location.href = "/";                       // back to the landing page
  };

  const workspace: Workspace = {
    health,
    backendDown: !!healthError && healthError.status !== 401,
    projects,
    workers,
    approvals,
    reloadProjects,
    reloadWorkers,
    reloadApprovals,
  };

  const online = (workers ?? []).filter((w) => w.status === "online" && !w.revoked);
  const lastSeen = (workers ?? []).filter((w) => !w.revoked)[0];
  const recent = (projects ?? []).filter((p) => p.latest_run).slice(0, 5);
  const pendingByRun = new Map<string, number>();
  for (const a of approvals ?? []) if (a.run_id) pendingByRun.set(a.run_id, (pendingByRun.get(a.run_id) ?? 0) + 1);
  const waiting = approvals?.length ?? 0;

  return (
    <WorkspaceContext.Provider value={workspace}>
      <div className="v2 min-h-[100dvh]">
        <a
          href="#v2-main"
          className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-[60] focus:px-3 focus:py-2 focus:rounded-[7px] focus:bg-v2-surface focus:text-v2-text"
        >
          Skip to content
        </a>

        {/* Navigation rail: wide screens */}
        <aside className="hidden lg:flex fixed inset-y-0 left-0 z-30 w-[248px] flex-col bg-v2-fill border-r border-v2-line/[0.08] px-3.5 pt-5 pb-3.5">
          <div className="px-2">
            <EvoMark />
          </div>

          <nav aria-label="Workspace" className="mt-8 space-y-0.5">
            {NAV.map(({ href, label, icon: Icon, match }) => {
              const on = match(pathname);
              return (
                <Link
                  key={href}
                  href={href}
                  aria-current={on ? "page" : undefined}
                  className={cn(
                    "flex items-center gap-2.5 h-10 px-3 rounded-[7px] text-[14px] transition-colors",
                    on ? "bg-v2-accent/[0.09] text-v2-accent font-semibold" : "text-v2-text2 font-medium hover:bg-v2-line/[0.04] hover:text-v2-text",
                  )}
                >
                  <Icon size={18} weight={on ? "fill" : "regular"} />
                  {label}
                  {href === "/dashboard" && waiting > 0 && (
                    <span className="ml-auto min-w-[20px] h-5 px-1.5 rounded-full bg-v2-orange text-v2-bg text-[11px] font-semibold flex items-center justify-center tnum">
                      {waiting}
                      <span className="sr-only"> waiting for your decision</span>
                    </span>
                  )}
                </Link>
              );
            })}
          </nav>

          <div className="h-px bg-v2-line/[0.08] mx-1.5 my-5" />

          <Link
            href="/dashboard#laptop"
            className="flex items-center gap-2.5 px-3 py-2.5 rounded-[8px] bg-v2-line/[0.035] hover:bg-v2-line/[0.06] transition-colors"
          >
            <span className={cn("w-2 h-2 rounded-full shrink-0", online.length ? "bg-v2-accent v2-pulse" : "bg-v2-text3/50")} aria-hidden />
            <span className="min-w-0">
              <span className="block text-[13px] font-semibold text-v2-text truncate">{online.length ? "Laptop online" : "No laptop online"}</span>
              <span className="block text-[12px] text-v2-text3 truncate">
                {online.length
                  ? `${online[0].name}, checked in ${ago(online[0].last_heartbeat)}`
                  : lastSeen
                    ? `${lastSeen.name}, last seen ${ago(lastSeen.last_heartbeat)}`
                    : "Pair one from Overview"}
              </span>
            </span>
          </Link>

          {recent.length > 0 && (
            <div className="mt-6 min-h-0 flex-1 overflow-y-auto v2-scroll -mx-1 px-1">
              <h2 className="px-3 mb-1.5 text-[13px] font-semibold text-v2-text3">Recent runs</h2>
              <ul className="space-y-0.5">
                {recent.map((p) => {
                  const r = p.latest_run!;
                  const href = `/runs/${r.id}`;
                  const on = pathname === href;
                  const wait = pendingByRun.get(r.id) ?? 0;
                  return (
                    <li key={r.id}>
                      <Link
                        href={href}
                        aria-current={on ? "page" : undefined}
                        className={cn("flex items-start gap-2.5 px-3 py-2 rounded-[7px] transition-colors", on ? "bg-v2-line/[0.06]" : "hover:bg-v2-line/[0.04]")}
                      >
                        <span className={cn("mt-[7px] w-1.5 h-1.5 rounded-full shrink-0", TONE_FILL[wait ? "orange" : toneOf(r.status)])} aria-hidden />
                        <span className="min-w-0 flex-1">
                          <span className="block text-[13px] text-v2-text truncate">{p.goal ?? p.name}</span>
                          <span className="block text-[12px] text-v2-text3">
                            {wait ? `${wait} to decide` : statusLabel(r.status)}, {ago(r.started_at)}
                          </span>
                        </span>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}

          <button
            type="button"
            onClick={signOut}
            className="mt-auto flex items-center gap-2.5 h-10 px-3 rounded-[7px] text-[14px] text-v2-text3 hover:bg-v2-line/[0.04] hover:text-v2-text"
          >
            <SignOut size={18} /> Sign out
          </button>
        </aside>

        <div className="lg:pl-[248px] flex flex-col min-h-[100dvh]">
          {/* Top bar */}
          <header className="sticky top-0 z-20 h-14 v2-material border-b border-v2-line/[0.08] flex items-center gap-3 px-4 sm:px-6 lg:px-8">
            <div className="lg:hidden">
              <EvoMark compact />
            </div>
            <nav aria-label="Breadcrumb" className="flex items-center gap-2 text-[13px] text-v2-text3 min-w-0">
              <Link href="/dashboard" className="hidden sm:inline hover:text-v2-text">
                Workspace
              </Link>
              <span className="hidden sm:inline" aria-hidden>
                /
              </span>
              <span className="font-semibold text-v2-text2 truncate">{crumb(pathname)}</span>
            </nav>
            <div className="ml-auto flex items-center gap-1">
              <span className={cn("hidden sm:flex items-center gap-2 text-[13px] pr-2", online.length ? "text-v2-text2" : "text-v2-text3")}>
                <Laptop size={18} className={online.length ? "text-v2-accent" : undefined} />
                {online.length ? online[0].name : "No laptop online"}
              </span>
              <button
                type="button"
                onClick={signOut}
                aria-label="Sign out"
                title="Sign out"
                className="lg:hidden w-9 h-9 flex items-center justify-center rounded-[7px] text-v2-text3 hover:bg-v2-line/[0.06]"
              >
                <SignOut size={18} />
              </button>
            </div>
          </header>

          {health?.mode === "simulated" && (
            <div className="bg-v2-gold/[0.12] border-b border-v2-gold/25 text-v2-orange text-[13px] text-center px-4 py-2 font-medium">
              Simulated mode: scripted AI replies and a simulated laptop. The pipeline code is real.
            </div>
          )}
          {workspace.backendDown && (
            <div
              className="bg-v2-red/[0.08] border-b border-v2-red/20 text-v2-red text-[13px] px-4 py-2 flex items-center justify-center gap-2 font-medium"
              role="alert"
            >
              <WarningCircle size={16} weight="fill" />
              Can&apos;t reach the backend. Start it from backend/ with: py -m uvicorn app.main:app --port 8000
            </div>
          )}

          <main id="v2-main" className="flex-1 w-full max-w-[1180px] mx-auto px-4 sm:px-6 lg:px-12 pt-7 lg:pt-10 pb-28 lg:pb-16">
            {children}
          </main>
        </div>

        {/* Tab bar: narrow screens */}
        <nav aria-label="Workspace" className="lg:hidden fixed bottom-0 inset-x-0 z-30 v2-material border-t border-v2-line/[0.08] pb-[env(safe-area-inset-bottom)]">
          <div className="grid grid-cols-3">
            {NAV.map(({ href, label, icon: Icon, match }) => {
              const on = match(pathname);
              return (
                <Link
                  key={href}
                  href={href}
                  aria-current={on ? "page" : undefined}
                  className={cn("relative flex flex-col items-center justify-center gap-0.5 h-14 text-[12px] font-medium", on ? "text-v2-accent" : "text-v2-text3")}
                >
                  <Icon size={22} weight={on ? "fill" : "regular"} />
                  {label}
                  {href === "/dashboard" && waiting > 0 && (
                    <span className="absolute top-1.5 left-1/2 ml-2 min-w-[18px] h-[18px] px-1 rounded-full bg-v2-orange text-v2-bg text-[11px] font-semibold flex items-center justify-center tnum">
                      {waiting}
                    </span>
                  )}
                </Link>
              );
            })}
          </div>
        </nav>
      </div>
    </WorkspaceContext.Provider>
  );
}
