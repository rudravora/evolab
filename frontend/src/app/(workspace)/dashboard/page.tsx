"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  ArrowUpRight,
  Books,
  Check,
  Clock,
  Code,
  Copy,
  Database,
  FileText,
  GitBranch,
  Laptop,
  NotePencil,
  Plus,
  Question,
  Scroll,
  Sparkle,
} from "@phosphor-icons/react";
import { api, ApiError } from "@/lib/api";
import { usePoll } from "@/lib/hooks";
import type { Agent, Project, StreamEvent, Task, Worker } from "@/lib/types";
import { cn } from "@/lib/utils";
import { ago, isFinal, minutes, sentence, statusLabel, type LedgerEntry } from "@/lib/workspace/model";
import { useWorkspace } from "@/components/workspace/Shell";
import { Approval } from "@/components/workspace/Approval";
import { Activity, KEY_EVENTS, RunStrip } from "@/components/workspace/RunBits";
import { Dialog } from "@/components/workspace/Sheet";
import { Button, buttonStyles, Empty, FieldLabel, Meter, Panel, Segmented, Skeleton, StatusBadge, TextArea, TextField } from "@/components/workspace/ui";

interface EventRow {
  id: number;
  ts: string;
  type: string;
  payload: Record<string, unknown>;
}
interface MemoryEntry {
  id: string;
  kind: string;
  source: "seeded" | "learned";
  content: Record<string, unknown>;
  created_at: string;
}

export default function OverviewV2() {
  const { projects, workers, approvals, reloadApprovals, reloadProjects } = useWorkspace();
  const [intake, setIntake] = React.useState(false);
  const runs = (projects ?? []).filter((p) => p.latest_run);
  const current = runs.find((p) => !isFinal(p.latest_run!.status)) ?? runs[0];
  // Formatted in the browser only: the server's locale can differ, which would break hydration.
  const [today, setToday] = React.useState("");
  React.useEffect(() => setToday(new Date().toLocaleDateString([], { weekday: "long", month: "long", day: "numeric" })), []);

  return (
    <div className="space-y-5">
      <header className="flex flex-col sm:flex-row sm:items-end justify-between gap-5 pb-3">
        <div>
          <p className="v2-mono text-[12px] uppercase tracking-[0.12em] text-v2-text3 min-h-[18px]">{today}</p>
          <h1 className="mt-3 text-[38px] sm:text-[44px] font-medium leading-[1.02] tracking-[-0.055em] text-v2-text">
            Your research, <em className="v2-serif italic text-v2-accent">in motion.</em>
          </h1>
          <p className="text-[15px] text-v2-text2 mt-2.5">What is running, what changed, and what needs your call.</p>
        </div>
        <Button kind="primary" size="lg" onClick={() => setIntake(true)} className="self-start sm:self-auto">
          <Plus size={16} weight="bold" /> New research
        </Button>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1.55fr)_minmax(280px,0.8fr)] gap-4">
        <CurrentRun project={current} loading={!projects} />
        <LaptopCard workers={workers} />
      </div>

      {(approvals ?? []).length > 0 && (
        <section aria-label="Decisions waiting" className="space-y-3 pt-1">
          {approvals!.slice(0, 3).map((a) => (
            <div key={a.id}>
              <Approval
                approval={a}
                onDone={() => {
                  reloadApprovals();
                  reloadProjects();
                }}
              />
              {a.run_id && (
                <Link href={`/runs/${a.run_id}`} className="inline-flex items-center gap-1 mt-1.5 ml-1 text-[13px] text-v2-accent font-semibold hover:gap-1.5 transition-[gap]">
                  Open the run for full context <ArrowRight size={13} />
                </Link>
              )}
            </div>
          ))}
        </section>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,0.85fr)] gap-4 pt-1 items-start">
        <RunsPanel runs={runs} loading={!projects} />
        <ChangesPanel runId={current?.latest_run?.id} />
      </div>

      <TeamStrip />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 items-start">
        <MemoryPanel />
        <LedgerPanel runId={current?.latest_run?.id} />
      </div>

      {intake && <IntakeDialog onClose={() => setIntake(false)} />}
    </div>
  );
}

/* ---------- current run (the ink card) ---------- */

function CurrentRun({ project: p, loading }: { project?: Project; loading: boolean }) {
  const r = p?.latest_run ?? null;
  const { data: tasks } = usePoll<Task[]>(r ? `/runs/${r.id}/tasks` : null, 10000);
  if (loading) return <Skeleton className="min-h-[220px] rounded-[10px]" />;
  if (!p || !r)
    return (
      <div className="rounded-[10px] bg-v2-inkcard text-v2-inkcardtext p-6 flex flex-col justify-between min-h-[220px]">
        <div>
          <p className="text-[13px] text-v2-inkcardmuted">No runs yet</p>
          <p className="v2-serif italic text-[24px] leading-snug mt-3 text-v2-inkcardtext">Start with a paper, a repository, a dataset or a question.</p>
        </div>
        <p className="text-[13px] text-v2-inkcardmuted">EvoLab builds a brief, drafts a plan for your approval, then runs it on your laptop.</p>
      </div>
    );

  const plan = (tasks ?? []).filter((t) => t.graph_key);
  const done = plan.filter((t) => ["done", "skipped"].includes(t.status)).length;
  const now = plan.find((t) => ["running", "waiting_for_job", "waiting_for_approval"].includes(t.status));
  const live = !isFinal(r.status);
  const title = p.name && p.name !== p.goal ? p.name : null;

  return (
    <Link
      href={`/runs/${r.id}`}
      className="group block rounded-[10px] bg-v2-inkcard text-v2-inkcardtext px-6 pt-5 pb-5 min-h-[220px] transition-[transform,box-shadow] duration-200 hover:-translate-y-0.5 hover:shadow-[0_12px_26px_rgb(24_36_33/0.12)]"
    >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="text-[13px] text-v2-inkcardmuted">{live ? "Current run" : "Latest run"}</p>
          {title && <h2 className="text-[16px] font-semibold mt-1 truncate">{title}</h2>}
        </div>
        <span className="inline-flex items-center gap-1.5 h-6 px-2.5 rounded-full border border-white/20 text-[12px] text-[#D6EADF] whitespace-nowrap">
          {live && <span className="w-1.5 h-1.5 rounded-full bg-[#55B597] v2-pulse" aria-hidden />}
          {r.counts.pending_approvals ? "Needs your decision" : statusLabel(r.status)}
        </span>
      </div>
      <p className="v2-serif italic text-[22px] sm:text-[24px] leading-snug mt-4 text-[#DCE6DF] max-w-[40ch]">&ldquo;{p.goal ?? p.name}&rdquo;</p>
      <div className="flex justify-between text-[13px] text-v2-inkcardmuted mt-5 mb-2">
        <span>{now ? `Now: ${sentence(now.task_type).toLowerCase()}` : plan.length ? "Plan" : r.status === "planning" ? "Drafting the plan" : "Plan"}</span>
        <span className="v2-mono">{plan.length ? `${done}/${plan.length}` : ""}</span>
      </div>
      <RunStrip tasks={plan} onDark size="sm" />
      <div className="flex flex-wrap items-center justify-between gap-x-5 gap-y-2 mt-4 text-[13px] text-v2-inkcardmuted">
        <div className="flex flex-wrap items-center gap-x-5 gap-y-1.5">
          <span className="inline-flex items-center gap-1.5">
            <Clock size={15} /> {minutes(r.usage.wall_min)}
            {r.budget.max_wall_min ? ` of ${r.budget.max_wall_min} min` : ""}
          </span>
          <span className="inline-flex items-center gap-1.5">
            <GitBranch size={15} /> {r.counts.branches} {r.counts.branches === 1 ? "branch" : "branches"}
          </span>
          <span className="inline-flex items-center gap-1.5">
            <Laptop size={15} /> {r.usage.jobs} {r.usage.jobs === 1 ? "job" : "jobs"}
          </span>
        </div>
        <span className="inline-flex items-center gap-1 text-[#BDE2CF] font-semibold group-hover:gap-1.5 transition-[gap]">
          Open run <ArrowUpRight size={15} />
        </span>
      </div>
    </Link>
  );
}

/* ---------- laptop ---------- */

interface Pairing {
  pairing_code: string;
  expires_at: string;
  command: string;
}

function LaptopCard({ workers }: { workers?: Worker[] }) {
  const { reloadWorkers } = useWorkspace();
  const [pairing, setPairing] = React.useState<Pairing | null>(null);
  const [pairErr, setPairErr] = React.useState<string | null>(null);
  const [copied, setCopied] = React.useState(false);
  const [confirmRevoke, setConfirmRevoke] = React.useState(false);
  const live = (workers ?? []).filter((w) => !w.revoked);
  const w = live.find((x) => x.status === "online");

  const pair = async () => {
    setPairErr(null);
    try {
      setPairing(await api<Pairing>("/workers/pairing", "POST"));
    } catch (e) {
      setPairErr(e instanceof ApiError ? e.message : "Couldn't create a pairing code. Try again.");
    }
  };
  const backend = pairing?.command.match(/BACKEND_URL=(\S+)/)?.[1] ?? "http://localhost:8000";
  const ps = pairing
    ? `$env:BACKEND_URL = "${backend}"; $env:PAIRING_CODE = "${pairing.pairing_code}"; $env:WORKSPACE_ROOT = "$PWD\\workspace"; py worker\\worker.py`
    : "";
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(ps);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      /* clipboard blocked: the command is still selectable */
    }
  };
  const revoke = async (id: string) => {
    await api(`/workers/${id}`, "DELETE").catch(() => undefined);
    setConfirmRevoke(false);
    reloadWorkers();
  };

  return (
    <section id="laptop" aria-labelledby="laptop-h" className="v2-card px-5 pt-[18px] pb-4 flex flex-col min-h-[220px] scroll-mt-20">
      <div className="flex items-center justify-between">
        <h2 id="laptop-h" className="text-[15px] font-semibold text-v2-text">
          Your laptop
        </h2>
        {w ? <StatusBadge status="online" label="Online" /> : workers && <StatusBadge status="offline" label="Offline" />}
      </div>

      {!workers ? (
        <Skeleton className="h-28 mt-4" />
      ) : w ? (
        <>
          <div className="flex items-center gap-3 mt-4">
            <span className="w-10 h-10 rounded-[8px] bg-v2-raised text-v2-text2 flex items-center justify-center shrink-0" aria-hidden>
              <Laptop size={20} />
            </span>
            <div className="min-w-0">
              <div className="text-[15px] font-semibold text-v2-text truncate">{w.name}</div>
              <div className="text-[13px] text-v2-text3 truncate">
                {w.platform}, {w.capabilities?.cpu_cores ?? "?"} cores{w.capabilities?.ram_gb ? `, ${w.capabilities.ram_gb} GB` : ""}
              </div>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-5 mt-4">
            {[
              ["CPU", w.cpu_pct],
              ["Memory", w.ram_pct],
            ].map(([label, v]) => (
              <div key={label as string}>
                <div className="flex justify-between text-[12px] text-v2-text3 mb-1.5">
                  <span>{label}</span>
                  <span className="v2-mono text-v2-text">{v != null ? `${Math.round(v as number)}%` : "-"}</span>
                </div>
                <Meter value={v != null ? (v as number) / 100 : null} label={`${label} use`} />
              </div>
            ))}
          </div>
          <div className="mt-auto pt-3 border-t border-v2-line/[0.07] flex flex-wrap items-center justify-between gap-2 text-[12px] text-v2-text3">
            <span>Checked in {ago(w.last_heartbeat)}</span>
            {confirmRevoke ? (
              <span className="flex items-center gap-1.5">
                <Button size="sm" onClick={() => setConfirmRevoke(false)}>
                  Keep
                </Button>
                <Button size="sm" kind="destructive" onClick={() => revoke(w.id)}>
                  Disconnect
                </Button>
              </span>
            ) : (
              <button type="button" onClick={() => setConfirmRevoke(true)} className="text-v2-red font-semibold hover:underline underline-offset-2">
                Disconnect
              </button>
            )}
          </div>
        </>
      ) : !pairing ? (
        <div className="mt-4 flex flex-col flex-1">
          <p className="text-[14px] text-v2-text2">
            {live.length ? `${live[0].name} was last seen ${ago(live[0].last_heartbeat)}.` : "No laptop is paired."} Planning works without one;
            experiments wait for it.
          </p>
          <p className="text-[13px] text-v2-text3 mt-2">Jobs run inside a locked folder on the laptop. It only reaches out; nothing connects in.</p>
          <Button kind="primary" className="mt-auto w-full" onClick={pair}>
            Pair a laptop
          </Button>
          {pairErr && (
            <p className="text-[13px] text-v2-red mt-2" role="alert">
              {pairErr}
            </p>
          )}
        </div>
      ) : (
        <ol className="mt-4 space-y-3.5 text-[13px] text-v2-text2">
          <li>
            <span className="font-semibold text-v2-text">Code</span>
            <span className="v2-mono text-[20px] font-medium tracking-[0.06em] text-v2-text ml-3">{pairing.pairing_code}</span>
            <span className="text-v2-text3 ml-2">valid 10 min</span>
          </li>
          <li>
            <span className="font-semibold text-v2-text">In PowerShell, from the EvoLab folder (the repo root):</span>
            <div className="relative mt-1.5">
              <pre className="v2-mono text-[12px] leading-relaxed bg-v2-raised rounded-[7px] p-3 pr-11 whitespace-pre-wrap break-all text-v2-text">{ps}</pre>
              <button
                type="button"
                onClick={copy}
                aria-label={copied ? "Copied" : "Copy command"}
                className="absolute top-2 right-2 w-8 h-8 rounded-[6px] flex items-center justify-center text-v2-text3 hover:bg-v2-line/[0.08]"
              >
                {copied ? <Check size={16} className="text-v2-accent" /> : <Copy size={16} />}
              </button>
            </div>
          </li>
          <li className="flex flex-wrap items-center gap-2">
            <span className="flex-1 min-w-[12ch]">Keep that window open.</span>
            <Button size="sm" onClick={reloadWorkers}>
              Check again
            </Button>
            <Button size="sm" kind="plain" onClick={pair}>
              New code
            </Button>
          </li>
        </ol>
      )}
    </section>
  );
}

/* ---------- runs ---------- */

function RunsPanel({ runs, loading }: { runs: Project[]; loading: boolean }) {
  return (
    <Panel title="Runs" detail={runs.length ? `${runs.length} in this workspace, newest first` : undefined} bodyClassName="px-0 pb-1 pt-2">
      {loading ? (
        <div className="px-5 pb-4 space-y-2">
          <Skeleton className="h-12" />
          <Skeleton className="h-12" />
        </div>
      ) : !runs.length ? (
        <Empty icon={<FileText size={28} />} title="No runs yet">
          Start one with New research.
        </Empty>
      ) : (
        <ul>
          {runs.slice(0, 8).map((p, i) => {
            const r = p.latest_run!;
            const wait = r.counts.pending_approvals;
            return (
              <li key={r.id} className="border-t border-v2-line/[0.06]">
                <Link href={`/runs/${r.id}`} className="flex items-center gap-3.5 px-5 py-3 hover:bg-v2-line/[0.025] transition-colors">
                  <span className="v2-mono w-6 text-[12px] text-v2-text3 shrink-0">
                    {!isFinal(r.status) ? <span className="block w-1.5 h-1.5 rounded-full bg-v2-accent v2-pulse ml-1" aria-label="In progress" /> : String(i + 1).padStart(2, "0")}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-[14px] font-medium text-v2-text truncate">{p.goal ?? p.name}</span>
                    <span className="block text-[12px] text-v2-text3 truncate">
                      {p.inputs.map((x) => sentence(x.kind)).join(", ") || "No inputs"}, {minutes(r.usage.wall_min)}
                    </span>
                  </span>
                  <StatusBadge status={wait ? "awaiting_approval" : r.status} label={wait ? `${wait} to decide` : undefined} />
                  <span className="hidden sm:block v2-mono text-[12px] text-v2-text3 w-[70px] text-right shrink-0">{ago(r.started_at)}</span>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </Panel>
  );
}

function ChangesPanel({ runId }: { runId?: string }) {
  const { data: rows } = usePoll<EventRow[]>(runId ? `/runs/${runId}/events?limit=1000` : null, 15000);
  const { data: graph } = usePoll<{ nodes: { id: string; name: string }[] }>(runId ? `/runs/${runId}/agent-graph` : null, 60000);
  const names = Object.fromEntries((graph?.nodes ?? []).map((n) => [n.id, n.name]));
  const events: StreamEvent[] = (rows ?? []).map((e) => ({ id: e.id, type: e.type, data: { ...e.payload, ts: e.ts } }));
  return (
    <Panel
      title="What changed"
      detail="Events from the latest run, each with its reason."
      action={
        runId ? (
          <Link href={`/runs/${runId}`} className="inline-flex items-center gap-1 text-[13px] text-v2-accent font-semibold">
            Timeline <ArrowUpRight size={14} />
          </Link>
        ) : undefined
      }
    >
      {!runId ? (
        <p className="text-[13px] text-v2-text3 py-6 text-center">Events appear once a run starts.</p>
      ) : !rows ? (
        <Skeleton className="h-40" />
      ) : (
        <Activity events={events} names={names} limit={7} maxHeight="max-h-[380px]" only={KEY_EVENTS} />
      )}
    </Panel>
  );
}

/* ---------- team, memory, ledger ---------- */

function TeamStrip() {
  const { data: agents } = usePoll<Agent[]>("/agents", 60000);
  const team = (agents ?? []).filter((a) => a.role !== "council_judge" && a.status === "active");
  const spawned = team.filter((a) => a.kind === "spawned").length;
  return (
    <section className="v2-card px-5 py-4 flex flex-col sm:flex-row sm:items-center gap-4" aria-labelledby="team-h">
      <div className="min-w-0">
        <h2 id="team-h" className="text-[15px] font-semibold text-v2-text">
          Agent team
        </h2>
        <p className="text-[13px] text-v2-text3 mt-0.5">
          {agents
            ? `${team.length} agents and a council of 3 judges${spawned ? `, ${spawned} written by evolution` : ""}.`
            : "Loading the team"}
        </p>
      </div>
      <div className="sm:ml-auto flex items-center gap-4">
        <ul className="flex -space-x-1.5" aria-label="Some of the agents">
          {team.slice(0, 6).map((a, i) => (
            <li
              key={a.id}
              title={a.name}
              className={cn(
                "w-8 h-8 rounded-full border-2 border-v2-surface flex items-center justify-center text-[12px] font-semibold",
                a.kind === "spawned"
                  ? "bg-v2-purple/[0.15] text-v2-purple"
                  : ["bg-v2-accent/[0.12] text-v2-accent", "bg-v2-gold/[0.16] text-v2-orange", "bg-v2-line/[0.08] text-v2-text2"][i % 3],
              )}
            >
              {a.name.charAt(0)}
            </li>
          ))}
        </ul>
        <Link href="/agents" className={buttonStyles("secondary", "sm")}>
          See the team <ArrowRight size={14} />
        </Link>
      </div>
    </section>
  );
}

function headline(c: Record<string, unknown>, kind: string) {
  for (const k of ["summary", "lesson", "title", "fix", "error", "description"]) if (typeof c[k] === "string" && c[k]) return String(c[k]);
  const first = Object.values(c).find((v) => typeof v === "string" && v.length < 160);
  return typeof first === "string" ? first : sentence(kind);
}

function MemoryPanel() {
  const { data } = usePoll<{ entries: MemoryEntry[]; counts?: { seeded: number; learned: number } }>("/memory", 60000);
  const entries = (data?.entries ?? []).slice(0, 3);
  return (
    <Panel
      title="Memory"
      detail={data?.counts ? `${data.counts.learned} learned, ${data.counts.seeded} seeded. Saved only after a fix is verified.` : "Saved only after a fix is verified."}
      action={
        <Link href="/memory" className="inline-flex items-center gap-1 text-[13px] text-v2-accent font-semibold">
          All <ArrowUpRight size={14} />
        </Link>
      }
      bodyClassName="px-0 pb-1 pt-2"
    >
      {!data ? (
        <div className="px-5 pb-4">
          <Skeleton className="h-24" />
        </div>
      ) : !entries.length ? (
        <p className="text-[13px] text-v2-text3 px-5 pb-5 pt-2">No lessons yet. They appear when the Debugger fixes a failure and the re-run passes.</p>
      ) : (
        <ul>
          {entries.map((e) => (
            <li key={e.id} className="border-t border-v2-line/[0.06] px-5 py-3 flex items-start gap-3">
              <Books size={18} className="text-v2-text3 mt-0.5 shrink-0" />
              <div className="min-w-0 flex-1">
                <p className="text-[14px] text-v2-text truncate">{headline(e.content, e.kind)}</p>
                <p className="text-[12px] text-v2-text3">
                  {sentence(e.kind)}, {ago(e.created_at)}
                </p>
              </div>
              <StatusBadge status={e.source === "learned" ? "done" : "proposed"} label={e.source === "learned" ? "Learned" : "Seeded"} />
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

function LedgerPanel({ runId }: { runId?: string }) {
  const { data } = usePoll<LedgerEntry[]>(runId ? `/runs/${runId}/ledger` : null, 30000);
  return (
    <Panel
      title="Ledger"
      detail="What differed from the paper or its code, and why."
      action={
        runId ? (
          <Link href={`/runs/${runId}#ledger`} className="inline-flex items-center gap-1 text-[13px] text-v2-accent font-semibold">
            All <ArrowUpRight size={14} />
          </Link>
        ) : undefined
      }
      bodyClassName="px-0 pb-1 pt-2"
    >
      {!runId ? (
        <p className="text-[13px] text-v2-text3 px-5 pb-5 pt-2">Deviations are recorded here as a run makes them.</p>
      ) : !data ? (
        <div className="px-5 pb-4">
          <Skeleton className="h-24" />
        </div>
      ) : !data.length ? (
        <p className="text-[13px] text-v2-text3 px-5 pb-5 pt-2">No deviations in the latest run.</p>
      ) : (
        <ul>
          {data.slice(-3).map((e) => (
            <li key={e.id} className="border-t border-v2-line/[0.06] px-5 py-3">
              <p className="text-[14px] text-v2-text">{e.description}</p>
              <p className="text-[12px] text-v2-orange font-medium mt-0.5">{sentence(e.category)}</p>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

/* ---------- intake dialog ---------- */

type Kind = "question" | "paper" | "repo" | "dataset" | "note";
const KINDS: { kind: Kind; label: string; icon: React.ElementType }[] = [
  { kind: "question", label: "Question", icon: Question },
  { kind: "paper", label: "Paper", icon: Scroll },
  { kind: "repo", label: "Code", icon: Code },
  { kind: "dataset", label: "Dataset", icon: Database },
  { kind: "note", label: "Note", icon: NotePencil },
];
const BUDGETS = [
  { value: "15", label: "15 min" },
  { value: "30", label: "30 min" },
  { value: "60", label: "1 hour" },
  { value: "120", label: "2 hours" },
];

function IntakeDialog({ onClose }: { onClose: () => void }) {
  const router = useRouter();
  const [on, setOn] = React.useState<Kind[]>(["question", "paper"]);
  const [val, setVal] = React.useState<Record<Kind, string>>({ question: "", paper: "", repo: "", dataset: "", note: "" });
  const [budget, setBudget] = React.useState("30");
  const [busy, setBusy] = React.useState<null | "custom" | "example">(null);
  const [err, setErr] = React.useState<string | null>(null);
  const [touched, setTouched] = React.useState(false);

  const filled = on.filter((k) => val[k].trim());
  const urlErr = (k: Kind) => (on.includes(k) && val[k].trim() && !/^https?:\/\//.test(val[k].trim()) ? "Use a full link, starting with https://" : null);
  const toggle = (k: Kind) => setOn((s) => (s.includes(k) ? s.filter((x) => x !== k) : [...s, k]));

  const start = async (example: boolean) => {
    if (!example) {
      setTouched(true);
      if (!filled.filter((k) => k !== "note").length || urlErr("paper") || urlErr("repo")) return;
    }
    setBusy(example ? "example" : "custom");
    setErr(null);
    try {
      const inputs = example
        ? []
        : filled.map((k) => {
            const ref = val[k].trim();
            if (k === "question" || k === "note") return { kind: k, source: "text", ref };
            if (k === "dataset") return { kind: k, source: ref.startsWith("http") ? "url" : "worker_path", ref };
            return { kind: k, source: "url", ref };
          });
      const min = Number(budget);
      const created = await api<{ run_id: string }>("/projects", "POST", {
        example,
        goal: example ? undefined : val.question.trim() || undefined,
        inputs,
        budget: { max_wall_min: min, max_tokens: 15000 * min },
      });
      router.push(`/runs/${created.run_id}`);
    } catch (e) {
      setErr(e instanceof ApiError ? `${e.message}.` : "Couldn't reach the backend. Check that it is running, then try again.");
      setBusy(null);
    }
  };

  const placeholder: Record<Kind, string> = {
    question: "Do KANs beat parameter-matched MLPs on tabular data?",
    paper: "https://arxiv.org/abs/2404.19756",
    repo: "https://github.com/KindXiaoming/pykan",
    dataset: "A link, or a path on the laptop such as C:\\data\\housing.csv",
    note: "Anything the team should know: constraints, what you already tried",
  };

  return (
    <Dialog title="What are we investigating?" intro="Combine inputs in any mix. EvoLab reads them into one research brief, then drafts a plan for your approval." onClose={onClose}>
      <div role="group" aria-label="Inputs to include" className="grid grid-cols-5 gap-2">
        {KINDS.map(({ kind, label, icon: Icon }) => {
          const sel = on.includes(kind);
          return (
            <button
              key={kind}
              type="button"
              aria-pressed={sel}
              onClick={() => toggle(kind)}
              className={cn(
                "relative flex flex-col items-center justify-center gap-1.5 h-[68px] rounded-[8px] border text-[13px] transition-colors",
                sel ? "border-v2-accent/50 bg-v2-accent/[0.07] text-v2-accent font-semibold" : "border-v2-line/[0.12] text-v2-text2 hover:border-v2-line/25",
              )}
            >
              <Icon size={20} weight={sel ? "duotone" : "regular"} />
              {label}
              {sel && <Check size={12} weight="bold" className="absolute top-1.5 right-1.5" aria-hidden />}
            </button>
          );
        })}
      </div>

      <form
        className="mt-5 space-y-4"
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          start(false);
        }}
      >
        {KINDS.filter((k) => on.includes(k.kind)).map(({ kind, label }) => {
          const id = `in-${kind}`;
          const bad = urlErr(kind);
          const long = kind === "question" || kind === "note";
          return (
            <div key={kind}>
              <FieldLabel htmlFor={id} hint={kind === "paper" ? "arXiv or PDF link" : kind === "repo" ? "GitHub link" : kind === "note" ? "optional" : undefined}>
                {kind === "question" ? "Research question" : kind === "note" ? "Context note" : label}
              </FieldLabel>
              {long ? (
                <TextArea
                  id={id}
                  rows={2}
                  value={val[kind]}
                  onChange={(e) => setVal({ ...val, [kind]: e.target.value })}
                  placeholder={placeholder[kind]}
                  data-autofocus={kind === on[0] ? true : undefined}
                />
              ) : (
                <TextField
                  id={id}
                  inputMode={kind === "dataset" ? undefined : "url"}
                  value={val[kind]}
                  aria-invalid={!!bad}
                  aria-describedby={bad ? `${id}-err` : undefined}
                  onChange={(e) => setVal({ ...val, [kind]: e.target.value })}
                  placeholder={placeholder[kind]}
                  data-autofocus={kind === on[0] ? true : undefined}
                />
              )}
              {bad && (
                <p id={`${id}-err`} className="text-[12px] text-v2-red mt-1">
                  {bad}
                </p>
              )}
            </div>
          );
        })}

        <div>
          <div className="text-[13px] font-semibold text-v2-text2 mb-1.5">Time budget</div>
          <Segmented label="Time budget" value={budget} onChange={setBudget} options={BUDGETS} />
        </div>

        {touched && !filled.filter((k) => k !== "note").length && (
          <p className="text-[13px] text-v2-red" role="alert">
            Fill in at least one of question, paper, code or dataset.
          </p>
        )}
        {err && (
          <p className="text-[13px] text-v2-red" role="alert">
            {err}
          </p>
        )}

        <div className="flex flex-wrap items-center justify-between gap-3 pt-4 border-t border-v2-line/[0.08]">
          <Button kind="plain" disabled={!!busy} onClick={() => start(true)} className="-ml-3">
            <Sparkle size={16} /> {busy === "example" ? "Starting" : "Try the KAN example"}
          </Button>
          <Button kind="primary" size="lg" type="submit" disabled={!!busy}>
            {busy === "custom" ? "Starting" : "Start research"} <ArrowRight size={16} />
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
