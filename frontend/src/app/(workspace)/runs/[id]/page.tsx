"use client";

import * as React from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  ArrowLeft,
  ArrowUpRight,
  ChatCircle,
  CheckCircle,
  Circle,
  CircleNotch,
  Clock,
  Code,
  Database,
  DownloadSimple,
  FileText,
  Pause,
  PaperPlaneRight,
  Play,
  Question,
  Scroll,
  ShieldCheck,
  Stop,
  Terminal,
  WarningCircle,
  Waveform,
} from "@phosphor-icons/react";
import { api, ApiError } from "@/lib/api";
import { usePoll, useRunStream } from "@/lib/hooks";
import type { AgentNode, Approval as ApprovalT, Brief, Project, Run, Task, TreeNode } from "@/lib/types";
import { cn } from "@/lib/utils";
import {
  bytes,
  compact,
  duration,
  hhmm,
  isFinal,
  minutes,
  num,
  ratio,
  sentence,
  statusLabel,
  taskWho,
  type Artifact,
  type ChatMessage,
  type Job,
  type LedgerEntry,
  type Report,
} from "@/lib/workspace/model";
import { useWorkspace } from "@/components/workspace/Shell";
import { Approval } from "@/components/workspace/Approval";
import { ExperimentTree, JobSheet, TaskSheet } from "@/components/workspace/Details";
import { Activity, Markdown, RunStrip } from "@/components/workspace/RunBits";
import { Button, Empty, Meter, Notice, Panel, Skeleton, StatusBadge } from "@/components/workspace/ui";

interface Revision {
  version: number;
  trigger: string | null;
  kind: string | null;
  reason: string | null;
  created_at: string;
}

// Refresh gaps per kind of data when events arrive, so a busy run stays well inside the
// dashboard rate limit (API.md 12). Polls are only the safety net.
const GAP: Record<string, number> = { tasks: 3000, approvals: 2000, run: 4000, tree: 5000, graph: 10000, brief: 10000, jobs: 4000, revisions: 5000 };

export default function RunV2() {
  const { id } = useParams<{ id: string }>();
  const { reloadApprovals: reloadInbox, reloadProjects } = useWorkspace();
  const { data: run, error: runError, reload: reloadRun } = usePoll<Run>(`/runs/${id}`, 15000);
  const { data: project } = usePoll<Project>(run ? `/projects/${run.project_id}` : null, 60000);
  const { data: tasks, reload: reloadTasks } = usePoll<Task[]>(`/runs/${id}/tasks`, 15000);
  const { data: approvals, reload: reloadApprovals } = usePoll<ApprovalT[]>(`/approvals?run_id=${id}&status=pending`, 15000);
  const { data: brief, reload: reloadBrief } = usePoll<Brief>(`/runs/${id}/brief`, 30000);
  const { data: tree, reload: reloadTree } = usePoll<{ roots: TreeNode[] }>(`/runs/${id}/tree`, 30000);
  const { data: graph, reload: reloadGraph } = usePoll<{ nodes: AgentNode[] }>(`/runs/${id}/agent-graph`, 30000);
  const { data: jobs, reload: reloadJobs } = usePoll<Job[]>(`/runs/${id}/jobs`, 20000);
  const { data: revisions, reload: reloadRevisions } = usePoll<Revision[]>(`/runs/${id}/plan/revisions`, 30000);
  const { events, connected, ended, lastType } = useRunStream(id);

  const last = React.useRef<Record<string, number>>({});
  React.useEffect(() => {
    if (!lastType) return;
    const t = lastType.type;
    const due = (k: string) => {
      const now = Date.now();
      if (now - (last.current[k] ?? 0) < GAP[k]) return false;
      last.current[k] = now;
      return true;
    };
    const timer = window.setTimeout(() => {
      if (["agent.task", "agent.score", "council.score", "plan.revised", "run.status"].includes(t) && due("tasks")) reloadTasks();
      if (["run.status", "job.status", "budget.warning", "agent.task"].includes(t) && due("run")) reloadRun();
      if (t.startsWith("approval.") && due("approvals")) {
        reloadApprovals();
        reloadInbox();
      }
      if (["branch.update", "experiment.metrics"].includes(t) && due("tree")) reloadTree();
      if (["agent.evolution", "agent.activation", "agent.score", "agent.probation"].includes(t) && due("graph")) reloadGraph();
      if (["intake.brief", "plan.revised"].includes(t) && due("brief")) reloadBrief();
      if (["job.status", "job.requeued"].includes(t) && due("jobs")) reloadJobs();
      if (["plan.revised", "approval.decided"].includes(t) && due("revisions")) reloadRevisions();
    }, 250);
    return () => window.clearTimeout(timer);
  }, [lastType, reloadTasks, reloadRun, reloadApprovals, reloadInbox, reloadTree, reloadGraph, reloadBrief, reloadJobs, reloadRevisions]);

  const [openTask, setOpenTask] = React.useState<string | null>(null);
  const [openJob, setOpenJob] = React.useState<Job | null>(null);
  const [confirmCancel, setConfirmCancel] = React.useState(false);
  const [controlErr, setControlErr] = React.useState<string | null>(null);

  const control = async (action: "pause" | "resume" | "cancel") => {
    setControlErr(null);
    try {
      await api(`/runs/${id}/${action}`, "POST");
      setConfirmCancel(false);
      reloadRun();
      reloadProjects();
    } catch (e) {
      setControlErr(e instanceof ApiError ? e.message : "The backend did not respond. Try again.");
    }
  };
  const branchControl = async (branchId: string, action: "pause" | "kill" | "expand") => {
    await api(`/branches/${branchId}/${action}`, "POST", action === "expand" ? { reason: "researcher override" } : undefined).catch(() => undefined);
    reloadTree();
  };

  if (runError?.status === 404) {
    return (
      <Empty title="Run not found" action={<Link href="/dashboard" className="text-v2-accent text-[14px] font-semibold">Back to Overview</Link>}>
        It may belong to a different database, for example the simulated backend.
      </Empty>
    );
  }

  const plan = (tasks ?? []).filter((t) => t.graph_key);
  const side = (tasks ?? []).filter((t) => !t.graph_key && t.task_type !== "intake");
  const done = plan.filter((t) => ["done", "skipped"].includes(t.status)).length;
  const pending = approvals ?? [];
  const final = isFinal(run?.status);
  const names = Object.fromEntries((graph?.nodes ?? []).map((n) => [n.id, n.name]));
  const planWaiting = pending.some((a) => a.type === "plan");
  const liveLabel = connected ? "Live" : ended || final ? "Finished" : "Reconnecting";

  return (
    <div>
      {/* breadcrumb */}
      <div className="flex items-center gap-2 text-[13px] text-v2-text3">
        <Link href="/dashboard" className="inline-flex items-center gap-1.5 text-v2-text2 hover:text-v2-accent">
          <ArrowLeft size={15} /> Overview
        </Link>
        <span aria-hidden>/</span>
        <span className="truncate">Run</span>
      </div>

      {/* title block */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-5 mt-5">
        <div className="min-w-0">
          <div className="flex items-center gap-2.5 text-[13px]">
            <span className="v2-mono text-v2-text3">{id.replace(/^run_/, "").slice(0, 10)}</span>
            <span className="w-1 h-1 rounded-full bg-v2-text3/50" aria-hidden />
            <span className={cn("inline-flex items-center gap-1.5 font-medium", connected ? "text-v2-accent" : "text-v2-text3")}>
              {connected && <span className="w-1.5 h-1.5 rounded-full bg-v2-accent v2-pulse" aria-hidden />}
              {liveLabel}
            </span>
          </div>
          {run ? (
            <h1 className="mt-2.5 text-[28px] sm:text-[34px] font-medium leading-[1.1] tracking-[-0.05em] text-v2-text max-w-[30ch]">
              {run.goal ?? "Research run"}
            </h1>
          ) : (
            <Skeleton className="h-10 w-96 max-w-full mt-2.5" />
          )}
          {run && (
            <div className="flex flex-wrap gap-x-5 gap-y-1.5 mt-3 text-[13px] text-v2-text3">
              <span className="inline-flex items-center gap-1.5">
                <Clock size={15} /> Started {new Date(run.started_at).toLocaleString([], { dateStyle: "medium", timeStyle: "short" })}
              </span>
              {project && project.inputs.length > 0 && (
                <span className="inline-flex items-center gap-1.5">
                  <FileText size={15} /> {project.inputs.map((i) => sentence(i.kind)).join(", ")}
                </span>
              )}
              {brief?.domain && (
                <span className="inline-flex items-center gap-1.5">
                  <ShieldCheck size={15} /> <span className="v2-mono">{brief.domain}</span>
                </span>
              )}
            </div>
          )}
        </div>
        {run && !final && (
          <div className="flex flex-wrap gap-2 shrink-0">
            {confirmCancel ? (
              <>
                <span className="self-center text-[13px] text-v2-text2 mr-1">Stop the run and its jobs?</span>
                <Button onClick={() => setConfirmCancel(false)}>Keep running</Button>
                <Button kind="destructive" onClick={() => control("cancel")}>
                  <Stop size={15} weight="fill" /> Cancel run
                </Button>
              </>
            ) : (
              <>
                <a
                  href="#chat"
                  className="inline-flex items-center gap-2 h-9 px-3.5 rounded-[7px] text-[13px] font-semibold bg-v2-surface text-v2-text2 border border-v2-line/[0.12] hover:text-v2-text"
                >
                  <ChatCircle size={16} /> Chat
                </a>
                {run.status === "running" && (
                  <Button kind="primary" onClick={() => control("pause")}>
                    <Pause size={15} weight="fill" /> Pause
                  </Button>
                )}
                {run.status === "paused" && (
                  <Button kind="primary" onClick={() => control("resume")}>
                    <Play size={15} weight="fill" /> Resume
                  </Button>
                )}
                <Button kind="destructive" onClick={() => setConfirmCancel(true)}>
                  <Stop size={15} weight="fill" /> Cancel
                </Button>
              </>
            )}
          </div>
        )}
      </div>
      {controlErr && (
        <p className="text-[13px] text-v2-red mt-2" role="alert">
          {controlErr}
        </p>
      )}

      {/* summary band */}
      <section aria-label="Run summary" className="v2-card mt-6 grid grid-cols-2 sm:grid-cols-4 xl:grid-cols-[auto_1fr_1fr_1fr_2fr] gap-x-6 gap-y-4 px-5 py-4 items-start">
        <div>
          <div className="text-[12px] text-v2-text3 mb-1.5">Status</div>
          {run ? (
            <StatusBadge status={pending.length ? "awaiting_approval" : run.status} label={pending.length ? "Needs your decision" : undefined} />
          ) : (
            <Skeleton className="h-6 w-20" />
          )}
        </div>
        <Figure label="Elapsed" value={run ? minutes(run.usage.wall_min) : "-"} />
        <Figure
          label="Budget"
          value={run?.budget.max_wall_min ? `${Math.round((ratio(run.usage.wall_min, run.budget.max_wall_min) ?? 0) * 100)}%` : "-"}
          sub={run?.budget.max_wall_min ? `of ${run.budget.max_wall_min} min` : undefined}
          meter={run ? ratio(run.usage.wall_min, run.budget.max_wall_min) : null}
        />
        <Figure
          label="AI tokens"
          value={run ? compact(run.usage.tokens) : "-"}
          sub={run?.budget.max_tokens ? `of ${compact(run.budget.max_tokens)}` : undefined}
          meter={run ? ratio(run.usage.tokens, run.budget.max_tokens) : null}
        />
        <div className="col-span-2 sm:col-span-4 xl:col-span-1 min-w-0">
          <div className="flex justify-between text-[12px] text-v2-text3 mb-2">
            <span>Overall progress</span>
            {plan.length ? (
              <span className="v2-mono text-v2-text">
                {done}/{plan.length}
              </span>
            ) : (
              <span>{planWaiting ? "Waiting for plan approval" : run?.status === "planning" ? "Drafting the plan" : ""}</span>
            )}
          </div>
          <RunStrip tasks={plan} onOpen={setOpenTask} size="sm" />
        </div>
      </section>

      {/* decisions */}
      {pending.length > 0 && (
        <section aria-label="Decisions waiting" className="space-y-3 mt-4">
          {pending.map((a) => (
            <Approval
              key={a.id}
              approval={a}
              onDone={() => {
                reloadApprovals();
                reloadInbox();
                reloadRun();
                reloadTasks();
                reloadRevisions();
              }}
            />
          ))}
        </section>
      )}

      {run?.status === "planning" && !pending.length && (
        <Notice tone="accent" className="mt-4" icon={<span className="block w-2 h-2 mt-1.5 rounded-full bg-v2-accent v2-pulse" />}>
          {brief?.ready
            ? "The AI manager is drafting the plan. It appears here for your approval."
            : "Reading the inputs: the paper, the code's README and the dataset, to build the research brief."}
        </Notice>
      )}

      <BriefCard brief={brief} project={project} />

      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1.63fr)_minmax(290px,0.76fr)] gap-4 mt-4 items-start">
        <div className="min-w-0 space-y-4">
          <PlanPanel plan={plan} side={side} loading={!tasks} onOpen={setOpenTask} jobs={jobs} onOpenJob={setOpenJob} />
          <Panel
            title="Branches"
            detail="The Designer proposes, the Evaluator scores, the Meta-Controller decides with evidence."
            action={tree?.roots.length ? <BranchCount roots={tree.roots} /> : undefined}
          >
            <ExperimentTree roots={tree?.roots ?? []} onControl={final ? undefined : branchControl} />
          </Panel>
          <ReportPanel runId={id} final={final} />
        </div>

        <aside className="min-w-0 space-y-4" aria-label="Run side panel">
          <RevisionsPanel revisions={revisions} />
          <TeamPanel nodes={graph?.nodes} />
          <JobsPanel jobs={jobs} onOpen={setOpenJob} />
          <LedgerPanel runId={id} />
          <Panel title="Activity" detail="Every event, newest first.">
            <Activity events={events} names={names} maxHeight="max-h-[420px]" />
          </Panel>
          <ChatPanel runId={id} disabled={final} />
        </aside>
      </div>

      {openTask && <TaskSheet taskId={openTask} onClose={() => setOpenTask(null)} />}
      {openJob && <JobSheet job={openJob} onClose={() => setOpenJob(null)} />}
    </div>
  );
}

function Figure({ label, value, sub, meter }: { label: string; value: string; sub?: string; meter?: number | null }) {
  return (
    <div className="min-w-0">
      <div className="text-[12px] text-v2-text3 mb-1">{label}</div>
      <div className="text-[18px] font-semibold tnum text-v2-text truncate leading-tight">
        {value} {sub && <span className="text-[12px] font-normal text-v2-text3">{sub}</span>}
      </div>
      {meter != null && <Meter value={meter} label={`${label} used`} className="mt-2" />}
    </div>
  );
}

function BranchCount({ roots }: { roots: TreeNode[] }) {
  const all: TreeNode[] = [];
  const walk = (n: TreeNode) => {
    all.push(n);
    n.children.forEach(walk);
  };
  roots.forEach(walk);
  const kids = all.filter((n) => !roots.includes(n));
  const expanded = kids.filter((n) => n.status === "expanded").length;
  return (
    <span className="text-[13px] text-v2-text3">
      {kids.length} proposed, {expanded} expanded
    </span>
  );
}

/* ---------- research brief ---------- */

const INPUT_ICON: Record<string, { icon: React.ElementType; cls: string }> = {
  paper: { icon: Scroll, cls: "bg-v2-gold/[0.14] text-v2-orange" },
  repo: { icon: Code, cls: "bg-v2-accent/[0.1] text-v2-accent" },
  dataset: { icon: Database, cls: "bg-v2-purple/[0.12] text-v2-purple" },
  question: { icon: Question, cls: "bg-v2-line/[0.06] text-v2-text2" },
  note: { icon: FileText, cls: "bg-v2-line/[0.06] text-v2-text2" },
};

function BriefCard({ brief, project }: { brief?: Brief; project?: Project }) {
  const inputs = project?.inputs ?? [];
  return (
    <Panel
      className="mt-4"
      title="Research brief"
      detail={brief?.ready ? "What intake found in your inputs." : "Intake is reading the inputs."}
      action={
        brief?.ready ? (
          <span className="inline-flex items-center gap-1.5 text-[13px] text-v2-accent font-medium">
            <CheckCircle size={16} weight="fill" /> Ready
          </span>
        ) : (
          <span className="inline-flex items-center gap-1.5 text-[13px] text-v2-text3">
            <CircleNotch size={16} className="animate-spin motion-reduce:animate-none" /> Reading
          </span>
        )
      }
    >
      {inputs.length > 0 && (
        <ul className="grid sm:grid-cols-2 xl:grid-cols-4 gap-2.5">
          {inputs.map((i) => {
            const m = INPUT_ICON[i.kind] ?? INPUT_ICON.note;
            const Icon = m.icon;
            const link = /^https?:\/\//.test(i.ref);
            const short = link ? i.ref.replace(/^https?:\/\/(www\.)?/, "") : i.ref;
            return (
              <li key={i.id} className="flex items-center gap-2.5 rounded-[8px] border border-v2-line/[0.07] bg-v2-raised/50 px-3 py-2.5 min-w-0">
                <span className={cn("w-8 h-8 rounded-[7px] flex items-center justify-center shrink-0", m.cls)} aria-hidden>
                  <Icon size={17} />
                </span>
                <span className="min-w-0">
                  <span className="block text-[12px] text-v2-text3">{sentence(i.kind === "repo" ? "code" : i.kind)}</span>
                  {link ? (
                    <a
                      href={i.ref}
                      target="_blank"
                      rel="noreferrer"
                      className="block text-[13px] font-semibold text-v2-text truncate hover:text-v2-accent"
                      title={i.ref}
                    >
                      {short}
                    </a>
                  ) : (
                    <span className="block text-[13px] font-semibold text-v2-text truncate" title={i.ref}>
                      {short}
                    </span>
                  )}
                </span>
              </li>
            );
          })}
        </ul>
      )}

      {brief?.ready && brief.facts.length > 0 && (
        <div className={cn(inputs.length > 0 && "mt-4 pt-4 border-t border-v2-line/[0.07]")}>
          <h3 className="text-[13px] font-semibold text-v2-text2 mb-2">Facts detected</h3>
          <ul className="grid md:grid-cols-2 gap-x-6 gap-y-2.5">
            {brief.facts.map((f, i) => (
              <li key={i} className="flex gap-2.5 text-[13px] min-w-0">
                <span className="mt-[7px] w-1.5 h-1.5 rounded-full bg-v2-accent shrink-0" aria-hidden />
                <span className="min-w-0">
                  <span className="font-semibold text-v2-text">{sentence(f.fact)}</span>
                  <span className="block text-v2-text3 break-words">{f.evidence}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {brief?.ready && (brief.reference_targets.length > 0 || brief.activation.length > 0) && (
        <details className="mt-4 pt-3 border-t border-v2-line/[0.07]">
          <summary className="cursor-pointer text-[13px] text-v2-accent font-semibold">Compared against, and who works on it</summary>
          <div className="grid md:grid-cols-2 gap-6 mt-3">
            {brief.reference_targets.length > 0 && (
              <div>
                <h3 className="text-[13px] font-semibold text-v2-text2 mb-2">Reference targets, best first</h3>
                <ol className="space-y-1.5 text-[13px]">
                  {brief.reference_targets.map((t) => (
                    <li key={t.rank} className="flex gap-2.5">
                      <span className="v2-mono text-v2-text3 w-5 shrink-0">{String(t.rank).padStart(2, "0")}</span>
                      <span className="text-v2-text">{sentence(t.type)}</span>
                    </li>
                  ))}
                </ol>
              </div>
            )}
            <div>
              <h3 className="text-[13px] font-semibold text-v2-text2 mb-2">Agents switched on, with the reason</h3>
              <ul className="space-y-1.5 text-[13px]">
                {brief.activation.map((a) => (
                  <li key={a.agent_id} className={cn(!a.active && "opacity-60")}>
                    <span className={cn("font-semibold", a.active ? "text-v2-text" : "text-v2-text3")}>
                      {sentence(a.agent_id.replace(/^agt_/, ""))}
                      {a.active ? "" : " (off)"}
                    </span>
                    <span className="text-v2-text3">: {a.reason}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </details>
      )}
    </Panel>
  );
}

/* ---------- execution plan ---------- */

function StateIcon({ status }: { status: string }) {
  if (status === "done")
    return (
      <span className="w-[22px] h-[22px] rounded-full bg-v2-green/[0.1] border border-v2-green/25 text-v2-green flex items-center justify-center">
        <CheckCircle size={14} weight="bold" />
      </span>
    );
  if (["running", "waiting_for_job"].includes(status))
    return (
      <span className="w-[22px] h-[22px] rounded-full bg-v2-surface border border-v2-accent/50 text-v2-accent flex items-center justify-center v2-pulse">
        <Waveform size={13} weight="bold" />
      </span>
    );
  if (["failed", "timed_out"].includes(status))
    return (
      <span className="w-[22px] h-[22px] rounded-full bg-v2-red/[0.1] border border-v2-red/25 text-v2-red flex items-center justify-center">
        <WarningCircle size={14} weight="bold" />
      </span>
    );
  if (status === "waiting_for_approval")
    return (
      <span className="w-[22px] h-[22px] rounded-full bg-v2-gold/[0.14] border border-v2-gold/30 text-v2-orange flex items-center justify-center">
        <Clock size={13} weight="bold" />
      </span>
    );
  return (
    <span className="w-[22px] h-[22px] rounded-full border border-v2-line/[0.15] bg-v2-surface text-v2-text3 flex items-center justify-center">
      <Circle size={7} weight="fill" className="opacity-50" />
    </span>
  );
}

function TaskTimeline({ tasks, onOpen }: { tasks: Task[]; onOpen: (id: string) => void }) {
  return (
    <ol>
      {tasks.map((t, i) => {
        const who = taskWho(t);
        return (
          <li key={t.id} className="relative flex gap-3.5">
            <div className="relative w-[22px] shrink-0 flex justify-center">
              <span className="relative z-[1] mt-3.5">
                <StateIcon status={t.status} />
              </span>
              {i < tasks.length - 1 && <span className="absolute top-[38px] bottom-0 w-px bg-v2-line/[0.1]" aria-hidden />}
            </div>
            <button
              type="button"
              onClick={() => onOpen(t.id)}
              className="flex-1 min-w-0 flex items-start gap-3 text-left py-3 border-b border-v2-line/[0.06] hover:bg-v2-line/[0.02] -mr-2 pr-2 rounded-[4px]"
            >
              <span className="min-w-0 flex-1">
                <span className="flex flex-wrap items-center gap-2">
                  <span className="text-[14px] font-semibold text-v2-text">{sentence(t.task_type)}</span>
                  <StatusBadge status={t.status} className="h-[22px] px-2 text-[12px]" />
                </span>
                <span className={cn("block text-[13px] mt-1", who === "Unassigned" ? "text-v2-orange font-medium" : "text-v2-text3")}>
                  {who}
                  {t.reward.reward !== null ? `, reward ${num(t.reward.reward)}` : ""}
                </span>
                {t.error && <span className="block text-[13px] text-v2-red mt-1 break-words">{t.error}</span>}
              </span>
              <span className="v2-mono text-[12px] text-v2-text3 shrink-0 pt-0.5">
                {t.ended_at ? duration(t.created_at, t.ended_at) : ["running", "waiting_for_job"].includes(t.status) ? hhmm(t.created_at) : ""}
              </span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}

function PlanPanel({
  plan,
  side,
  loading,
  onOpen,
  jobs,
  onOpenJob,
}: {
  plan: Task[];
  side: Task[];
  loading: boolean;
  onOpen: (id: string) => void;
  jobs?: Job[];
  onOpenJob: (j: Job) => void;
}) {
  const running = (jobs ?? []).find((j) => ["running", "claimed"].includes(j.status));
  return (
    <Panel
      title="Execution plan"
      detail="The approved task graph. Select a task to see who did it, how it scored and every step."
      bodyClassName="px-5 pb-0 pt-1"
    >
      {loading ? (
        <div className="space-y-2 pb-4">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-12" />
          ))}
        </div>
      ) : !plan.length && !side.length ? (
        <Empty title="No plan yet">Once you approve the plan, each task appears here in order.</Empty>
      ) : (
        <>
          {plan.length > 0 && <TaskTimeline tasks={plan} onOpen={onOpen} />}
          {side.length > 0 && (
            <details className="py-3">
              <summary className="cursor-pointer text-[13px] text-v2-accent font-semibold">
                Outside the plan: {side.length} planning, re-plan, fix and evolution {side.length === 1 ? "task" : "tasks"}
              </summary>
              <div className="mt-1">
                <TaskTimeline tasks={side} onOpen={onOpen} />
              </div>
            </details>
          )}
        </>
      )}
      {running && (
        <div className="flex flex-wrap items-center justify-between gap-2 py-3 border-t border-v2-line/[0.07] text-[13px] text-v2-text3">
          <span className="inline-flex items-center gap-2 min-w-0">
            <span className="w-1.5 h-1.5 rounded-full bg-v2-accent v2-pulse shrink-0" aria-hidden />
            Laptop job running: <span className="text-v2-text font-medium truncate">{sentence(running.type)}</span>
          </span>
          <button type="button" onClick={() => onOpenJob(running)} className="inline-flex items-center gap-1 text-v2-accent font-semibold">
            View log <ArrowUpRight size={14} />
          </button>
        </div>
      )}
    </Panel>
  );
}

/* ---------- side panels ---------- */

function RevisionsPanel({ revisions }: { revisions?: Revision[] }) {
  return (
    <Panel title="Plan timeline" detail="Every revision, with its trigger.">
      {!revisions ? (
        <Skeleton className="h-20" />
      ) : !revisions.length ? (
        <p className="text-[13px] text-v2-text3">The first version appears when you approve the plan.</p>
      ) : (
        <ol>
          {[...revisions].reverse().map((r, i, arr) => {
            const minor = r.kind === "minor";
            return (
              <li key={r.version} className="relative flex gap-3 pb-3.5">
                {i < arr.length - 1 && <span className="absolute left-[10px] top-[24px] bottom-0 w-px bg-v2-line/[0.1]" aria-hidden />}
                <span
                  className={cn(
                    "relative z-[1] w-[21px] h-[21px] rounded-full border flex items-center justify-center shrink-0 bg-v2-surface",
                    r.version === 1 || minor ? "border-v2-accent/40 text-v2-accent" : "border-v2-gold/40 text-v2-orange",
                  )}
                  aria-hidden
                >
                  <span className="v2-mono text-[11px]">{r.version}</span>
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="text-[14px] font-semibold text-v2-text">{r.version === 1 ? "Plan approved" : minor ? "Minor re-plan" : "Re-plan"}</span>
                    <time className="v2-mono text-[12px] text-v2-text3">{hhmm(r.created_at)}</time>
                  </div>
                  {r.reason && !/^plan approved\.?$/i.test(r.reason.trim()) && <p className="text-[13px] text-v2-text2 mt-0.5 break-words">{r.reason}</p>}
                  {r.trigger && <p className="text-[12px] text-v2-text3 mt-0.5">Trigger: {sentence(r.trigger).toLowerCase()}</p>}
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </Panel>
  );
}

function TeamPanel({ nodes }: { nodes?: AgentNode[] }) {
  const team = (nodes ?? []).filter((n) => n.role !== "council_judge");
  const working = team.filter((n) => n.active_in_run);
  const spawned = team.filter((n) => n.kind === "spawned");
  return (
    <Panel
      title="Agents"
      detail={nodes ? `${working.length} of ${team.length} on this run. Numbers are rolling reward.` : undefined}
      action={
        <Link href="/agents" className="inline-flex items-center gap-1 text-[13px] text-v2-accent font-semibold">
          Team <ArrowUpRight size={14} />
        </Link>
      }
      bodyClassName="px-0 pb-2 pt-1"
    >
      {!nodes ? (
        <div className="px-5 pb-3">
          <Skeleton className="h-24" />
        </div>
      ) : (
        <ul>
          {working.map((n, i) => (
            <li key={n.id} className="flex items-center gap-2.5 px-5 py-2 border-t border-v2-line/[0.06]" title={n.activation_reason ?? undefined}>
              <span
                className={cn(
                  "w-7 h-7 rounded-full flex items-center justify-center text-[12px] font-semibold shrink-0",
                  n.kind === "spawned"
                    ? "bg-v2-purple/[0.14] text-v2-purple"
                    : ["bg-v2-accent/[0.11] text-v2-accent", "bg-v2-gold/[0.15] text-v2-orange", "bg-v2-line/[0.07] text-v2-text2"][i % 3],
                )}
                aria-hidden
              >
                {n.name.charAt(0)}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block text-[13px] font-semibold text-v2-text truncate">{n.name}</span>
                <span className="block text-[12px] text-v2-text3 truncate">
                  {n.kind === "spawned" ? "Written by evolution" : n.kind === "seed" ? "Specialist" : sentence(n.kind)}
                  {n.status !== "active" ? `, ${statusLabel(n.status).toLowerCase()}` : ""}
                </span>
              </span>
              {n.rolling_reward !== null && <span className="v2-mono text-[13px] text-v2-text2">{num(n.rolling_reward)}</span>}
            </li>
          ))}
        </ul>
      )}
      {spawned.length > 0 && (
        <div className="mx-5 mt-2 mb-2 rounded-[7px] bg-v2-purple/[0.07] px-3 py-2.5 text-[13px]">
          <span className="font-semibold text-v2-purple">Lineage: </span>
          <span className="text-v2-text2">{spawned.map((n) => `${n.name} (${sentence(n.origin).toLowerCase()})`).join(", ")}</span>
        </div>
      )}
    </Panel>
  );
}

function JobsPanel({ jobs, onOpen }: { jobs?: Job[]; onOpen: (j: Job) => void }) {
  const sorted = [...(jobs ?? [])].sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at));
  const [all, setAll] = React.useState(false);
  const shown = all ? sorted : sorted.slice(0, 5);
  return (
    <Panel
      title="Laptop jobs"
      detail={jobs ? `${jobs.length} ${jobs.length === 1 ? "job" : "jobs"}, each inside the laptop's locked folder.` : undefined}
      bodyClassName="px-0 pb-2 pt-1"
    >
      {!jobs ? (
        <div className="px-5 pb-3">
          <Skeleton className="h-20" />
        </div>
      ) : !jobs.length ? (
        <p className="text-[13px] text-v2-text3 px-5 pb-3">Installs, downloads and experiments show up here with their logs.</p>
      ) : (
        <>
          <ul>
            {shown.map((j) => {
              const argv = Array.isArray(j.payload?.argv) ? (j.payload.argv as string[]).join(" ") : ((j.payload?.path as string | undefined) ?? "");
              return (
                <li key={j.id} className="border-t border-v2-line/[0.06]">
                  <button type="button" onClick={() => onOpen(j)} className="w-full flex items-center gap-3 px-5 py-2.5 text-left hover:bg-v2-line/[0.025]">
                    <Terminal size={16} className="text-v2-text3 shrink-0" />
                    <span className="min-w-0 flex-1">
                      <span className="block text-[13px] font-semibold text-v2-text">{sentence(j.type)}</span>
                      {argv && <span className="block v2-mono text-[12px] text-v2-text3 truncate">{argv}</span>}
                    </span>
                    <StatusBadge status={j.status} className="h-[22px] px-2" />
                  </button>
                </li>
              );
            })}
          </ul>
          {sorted.length > 5 && (
            <button type="button" onClick={() => setAll((v) => !v)} className="mx-5 mt-1 mb-1 text-[13px] text-v2-accent font-semibold">
              {all ? "Show fewer" : `Show all ${sorted.length}`}
            </button>
          )}
        </>
      )}
    </Panel>
  );
}

function LedgerPanel({ runId }: { runId: string }) {
  const { data } = usePoll<LedgerEntry[]>(`/runs/${runId}/ledger`, 20000);
  return (
    <Panel
      id="ledger"
      className="scroll-mt-20"
      title="Ledger"
      detail="Every change from the paper or its code, recorded when it was made."
      bodyClassName="px-0 pb-2 pt-1"
    >
      {!data ? (
        <div className="px-5 pb-3">
          <Skeleton className="h-16" />
        </div>
      ) : !data.length ? (
        <p className="text-[13px] text-v2-text3 px-5 pb-3">No deviations yet.</p>
      ) : (
        <ol>
          {data.map((e, i) => (
            <li key={e.id} className="flex gap-3 px-5 py-2.5 border-t border-v2-line/[0.06]">
              <span className="v2-mono text-[12px] text-v2-orange pt-px shrink-0">L{String(i + 1).padStart(2, "0")}</span>
              <span className="min-w-0">
                <span className="block text-[13px] font-semibold text-v2-text">{e.description}</span>
                <span className="block text-[12px] text-v2-text3">{sentence(e.category)}</span>
              </span>
            </li>
          ))}
        </ol>
      )}
    </Panel>
  );
}

function ReportPanel({ runId, final }: { runId: string; final: boolean }) {
  const { data, error } = usePoll<Report>(`/runs/${runId}/report`, final ? 60000 : 20000);
  const { data: files } = usePoll<Artifact[]>(`/runs/${runId}/artifacts`, final ? 60000 : 30000);
  const [full, setFull] = React.useState(false);
  const verdict = data?.markdown.match(/verdict:\s*\**\s*([a-z_ ]+)/i)?.[1]?.trim();
  const long = (data?.markdown.length ?? 0) > 1200;
  return (
    <Panel
      title="Report"
      detail={
        data
          ? `Written ${new Date(data.created_at).toLocaleString([], { dateStyle: "medium", timeStyle: "short" })}`
          : "The Reporter writes it at the end of the run."
      }
      action={
        verdict ? (
          <StatusBadge status={/^(reproduced|done)$/i.test(verdict) ? "done" : /not/i.test(verdict) ? "failed" : "proposed"} label={sentence(verdict)} />
        ) : undefined
      }
    >
      {error || !data ? (
        <Empty icon={<FileText size={28} />} title="No report yet">
          It is built from the experiments and the ledger, so every claim traces back to a result or a recorded change.
        </Empty>
      ) : (
        <>
          <div className={cn("relative", long && !full && "max-h-[360px] overflow-hidden")}>
            <Markdown text={data.markdown} />
            {long && !full && <div className="absolute inset-x-0 bottom-0 h-20 bg-gradient-to-t from-v2-surface to-transparent" aria-hidden />}
          </div>
          {long && (
            <button type="button" onClick={() => setFull((v) => !v)} className="mt-2 text-[13px] text-v2-accent font-semibold" aria-expanded={full}>
              {full ? "Show less" : "Read the full report"}
            </button>
          )}
          {data.why_differs.length > 0 && (
            <div className="mt-5 pt-4 border-t border-v2-line/[0.07]">
              <h3 className="text-[15px] font-semibold text-v2-text mb-2">Why results differ from the paper</h3>
              <ul className="list-disc pl-5 text-[14px] text-v2-text2 space-y-1">
                {data.why_differs.map((w) => (
                  <li key={w.ledger_entry_id}>{w.explanation}</li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
      {files && files.length > 0 && (
        <div className="mt-5 pt-4 border-t border-v2-line/[0.07]">
          <h3 className="text-[13px] font-semibold text-v2-text2 mb-2">Files</h3>
          <ul className="grid sm:grid-cols-2 gap-2">
            {files.map((f) => (
              <li key={f.id}>
                <a
                  href={`/api/v1/artifacts/${f.id}/download`}
                  className="flex items-center gap-2.5 rounded-[7px] border border-v2-line/[0.08] px-3 py-2 hover:border-v2-accent/40 transition-colors"
                >
                  <FileText size={17} className="text-v2-text3 shrink-0" />
                  <span className="min-w-0 flex-1">
                    <span className="block text-[13px] font-medium text-v2-text truncate">{f.name}</span>
                    <span className="block text-[12px] text-v2-text3">
                      {sentence(f.kind)}, {bytes(f.size)}
                    </span>
                  </span>
                  <DownloadSimple size={17} className="text-v2-accent shrink-0" aria-label="Download" />
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Panel>
  );
}

function ChatPanel({ runId, disabled }: { runId: string; disabled: boolean }) {
  const { data, reload } = usePoll<ChatMessage[]>(`/runs/${runId}/chat`, 20000);
  const [text, setText] = React.useState("");
  const [sending, setSending] = React.useState(false);
  const [err, setErr] = React.useState<string | null>(null);
  const list = React.useRef<HTMLOListElement>(null);
  React.useEffect(() => {
    list.current?.scrollTo({ top: list.current.scrollHeight });
  }, [data]);

  const send = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!text.trim()) return;
    setSending(true);
    setErr(null);
    try {
      await api(`/runs/${runId}/chat`, "POST", { message: text.trim() });
      setText("");
      reload();
    } catch (e2) {
      setErr(e2 instanceof ApiError ? e2.message : "Message not sent. Try again.");
    } finally {
      setSending(false);
    }
  };

  return (
    <Panel id="chat" className="scroll-mt-20" title="Ask the AI manager" detail="Request a change and the Meta-Controller re-plans, for example: try noisier data.">
      {data && data.length > 0 && (
        <ol ref={list} className="space-y-2 max-h-72 overflow-y-auto v2-scroll mb-3">
          {data.map((m) => {
            const mine = m.role === "researcher";
            return (
              <li key={m.id} className={cn("flex", mine ? "justify-end" : "justify-start")}>
                <div
                  className={cn(
                    "max-w-[88%] rounded-[10px] px-3 py-2 text-[13px] leading-snug break-words",
                    mine ? "bg-v2-accent text-v2-onaccent rounded-br-[3px]" : "bg-v2-raised text-v2-text rounded-bl-[3px]",
                  )}
                >
                  {m.content}
                </div>
              </li>
            );
          })}
        </ol>
      )}
      <form onSubmit={send} className="flex gap-2">
        <label htmlFor="chat-input" className="sr-only">
          Message the AI manager
        </label>
        <input
          id="chat-input"
          value={text}
          disabled={disabled}
          onChange={(e) => setText(e.target.value)}
          placeholder={disabled ? "This run has finished" : "Message"}
          className="flex-1 min-w-0 h-10 px-3 rounded-[7px] bg-v2-surface text-[14px] text-v2-text placeholder:text-v2-text3/80 border border-v2-line/[0.13] focus:outline-none focus:border-v2-accent focus:ring-[3px] focus:ring-v2-accent/15 disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={disabled || sending || !text.trim()}
          aria-label="Send"
          className="w-10 h-10 rounded-[7px] bg-v2-accent text-v2-onaccent flex items-center justify-center disabled:opacity-30 transition-opacity"
        >
          <PaperPlaneRight size={17} weight="fill" />
        </button>
      </form>
      {err && (
        <p className="text-[12px] text-v2-red mt-2" role="alert">
          {err}
        </p>
      )}
    </Panel>
  );
}
