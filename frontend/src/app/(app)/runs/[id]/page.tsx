"use client";

import * as React from "react";
import { useParams } from "next/navigation";
import { Pause, Play, Send, Square } from "lucide-react";
import { api } from "@/lib/api";
import { pct, usePoll, useRunStream } from "@/lib/hooks";
import type { AgentNode, Approval, Brief, Run, Task, TreeNode } from "@/lib/types";
import { ApprovalCard } from "@/components/app/ApprovalCard";
import { Btn, Empty, Label, Panel, Status, short } from "@/components/app/bits";
import { EventFeed, ExperimentTree, Markdown } from "@/components/app/RunParts";
import { TaskDrawer } from "@/components/app/TaskDrawer";
import { cn } from "@/lib/utils";

const TABS = ["Pipeline", "Experiments", "Brief", "Report", "Ledger"] as const;
type Tab = (typeof TABS)[number];
const EXECUTOR = new Set(["run_baseline", "run_branches"]);

export default function RunPage() {
  const { id } = useParams<{ id: string }>();
  // Slow polling is only a safety net; the live event stream triggers refreshes (see below).
  // Keeps the page well under the backend's 120 requests/minute per user (API.md 12).
  const { data: run, reload: reloadRun } = usePoll<Run>(`/runs/${id}`, 15000);
  const { data: tasks, reload: reloadTasks } = usePoll<Task[]>(`/runs/${id}/tasks`, 15000);
  const { data: approvals, reload: reloadApprovals } = usePoll<Approval[]>(`/approvals?run_id=${id}&status=pending`, 15000);
  const { data: brief, reload: reloadBrief } = usePoll<Brief>(`/runs/${id}/brief`, 30000);
  const { data: tree, reload: reloadTree } = usePoll<{ roots: TreeNode[] }>(`/runs/${id}/tree`, 30000);
  const { data: graph, reload: reloadGraph } = usePoll<{ nodes: AgentNode[] }>(`/runs/${id}/agent-graph`, 30000);
  const { events, connected, ended, lastType } = useRunStream(id);

  // Refresh from events, throttled per kind of data (3 to 10 seconds).
  const lastRefresh = React.useRef<Record<string, number>>({});
  React.useEffect(() => {
    if (!lastType) return;
    const t = lastType.type;
    const GAP: Record<string, number> = { tasks: 3000, approvals: 3000, run: 5000, tree: 5000, graph: 10000, brief: 10000 };
    const due = (key: string) => {
      const now = Date.now();
      if (now - (lastRefresh.current[key] ?? 0) < GAP[key]) return false;
      lastRefresh.current[key] = now;
      return true;
    };
    const timer = window.setTimeout(() => {
      if (["agent.task", "agent.score", "council.score", "plan.revised", "run.status"].includes(t) && due("tasks")) reloadTasks();
      if (["run.status", "job.status", "budget.warning"].includes(t) && due("run")) reloadRun();
      if (t.startsWith("approval.") && due("approvals")) reloadApprovals();
      if (["branch.update", "experiment.metrics"].includes(t) && due("tree")) reloadTree();
      if (["agent.evolution", "agent.activation", "agent.score"].includes(t) && due("graph")) reloadGraph();
      if (["intake.brief", "plan.revised"].includes(t) && due("brief")) reloadBrief();
    }, 300);
    return () => window.clearTimeout(timer);
  }, [lastType, reloadTasks, reloadRun, reloadApprovals, reloadTree, reloadGraph, reloadBrief]);
  const [tab, setTab] = React.useState<Tab>("Pipeline");
  const [openTask, setOpenTask] = React.useState<string | null>(null);

  const control = async (action: "pause" | "resume" | "cancel") => {
    if (action === "cancel" && !confirm("Cancel this run? Running jobs are stopped.")) return;
    await api(`/runs/${id}/${action}`, "POST").catch(() => undefined);
    reloadRun();
  };

  const graphTasks = (tasks ?? []).filter((t) => t.graph_key);
  const sideTasks = (tasks ?? []).filter((t) => !t.graph_key && t.task_type !== "intake");
  const done = graphTasks.filter((t) => ["done", "skipped"].includes(t.status)).length;

  return (
    <div className="space-y-5">
      {/* header */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <Label>Run {id}</Label>
          <h1 className="text-xl sm:text-2xl font-semibold tracking-tight">{run?.goal ?? "Research run"}</h1>
          <div className="flex flex-wrap items-center gap-3 mt-2 text-xs font-mono text-foreground-muted">
            {run && <Status value={run.status} />}
            {run && (
              <span>
                {run.usage.wall_min} / {run.budget.max_wall_min ?? "?"} min
              </span>
            )}
            {run && <span>{run.usage.tokens.toLocaleString()} AI tokens</span>}
            {run && <span>{run.usage.jobs} laptop jobs</span>}
            {graphTasks.length > 0 && (
              <span>
                {done}/{graphTasks.length} tasks
              </span>
            )}
            <span className={connected ? "text-emerald-300" : "text-foreground-faint"}>
              {connected ? "live" : ended ? "finished" : "reconnecting"}
            </span>
          </div>
        </div>
        <div className="flex gap-2">
          {run?.status === "running" && (
            <Btn onClick={() => control("pause")}>
              <Pause className="w-3.5 h-3.5" /> Pause
            </Btn>
          )}
          {run?.status === "paused" && (
            <Btn onClick={() => control("resume")}>
              <Play className="w-3.5 h-3.5" /> Resume
            </Btn>
          )}
          {run && !["done", "failed", "cancelled"].includes(run.status) && (
            <Btn variant="danger" onClick={() => control("cancel")}>
              <Square className="w-3.5 h-3.5" /> Cancel
            </Btn>
          )}
        </div>
      </div>

      {/* approvals first: nothing expensive runs without them */}
      {(approvals ?? []).length > 0 && (
        <div className="space-y-3">
          {approvals!.map((a) => (
            <ApprovalCard
              key={a.id}
              approval={a}
              onDone={() => {
                reloadApprovals();
                reloadRun();
              }}
            />
          ))}
        </div>
      )}
      {run?.status === "planning" && !(approvals ?? []).length && (
        <Panel>
          <div className="text-sm text-foreground-muted py-2">
            {brief?.ready
              ? "The Meta-Controller (the AI manager) is drafting the plan. It will appear here for your approval."
              : "Reading the inputs: fetching the paper, the README and the dataset details to build the Research Brief."}
          </div>
        </Panel>
      )}

      <div className="grid xl:grid-cols-3 gap-5">
        <div className="xl:col-span-2 space-y-5">
          <div className="flex gap-1 border-b border-border-subtle">
            {TABS.map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={cn(
                  "px-3 h-9 text-xs font-medium border-b-2 -mb-px transition-colors",
                  tab === t ? "border-cyan text-foreground" : "border-transparent text-foreground-muted hover:text-foreground",
                )}
              >
                {t}
              </button>
            ))}
          </div>

          {tab === "Pipeline" && (
            <Panel title="Plan and progress" action={<span className="text-[10px] font-mono text-foreground-faint">click a task to see why</span>}>
              {!graphTasks.length ? (
                <Empty>The pipeline appears once you approve the plan.</Empty>
              ) : (
                <div className="space-y-1">
                  {graphTasks.map((t) => (
                    <TaskRow key={t.id} t={t} onOpen={() => setOpenTask(t.id)} />
                  ))}
                </div>
              )}
              {sideTasks.length > 0 && (
                <>
                  <div className="mt-4 mb-1">
                    <Label>Outside the plan: planning, re-plans, debugging, evolution drafts</Label>
                  </div>
                  <div className="space-y-1">
                    {sideTasks.map((t) => (
                      <TaskRow key={t.id} t={t} onOpen={() => setOpenTask(t.id)} />
                    ))}
                  </div>
                </>
              )}
            </Panel>
          )}

          {tab === "Experiments" && (
            <Panel title="Exploration tree">
              <ExperimentTree roots={tree?.roots ?? []} />
            </Panel>
          )}

          {tab === "Brief" && <BriefView brief={brief} />}
          {tab === "Report" && <ReportView runId={id} />}
          {tab === "Ledger" && <LedgerView runId={id} />}
        </div>

        <div className="space-y-5">
          <Panel title="Agent team">
            <div className="space-y-1">
              {(graph?.nodes ?? [])
                .filter((n) => n.role !== "council_judge")
                .map((n) => (
                  <div key={n.id} className={cn("flex items-center gap-2 text-xs py-0.5", !n.active_in_run && "opacity-45")}>
                    <span
                      className={cn(
                        "w-1.5 h-1.5 rounded-full shrink-0",
                        n.kind === "spawned" ? "bg-amber" : n.active_in_run ? "bg-cyan" : "bg-foreground-faint",
                      )}
                    />
                    <span className={cn("truncate", n.kind === "spawned" && "text-amber-highlight")}>{n.name}</span>
                    {n.kind === "spawned" && <span className="text-[9px] font-mono text-amber-highlight">{n.origin}</span>}
                    {n.status !== "active" && <Status value={n.status} />}
                    <span className="ml-auto font-mono text-[10px] text-foreground-faint" title={n.activation_reason ?? ""}>
                      {n.rolling_reward !== null ? `R ${pct(n.rolling_reward)}` : n.active_in_run ? "" : "off"}
                    </span>
                  </div>
                ))}
            </div>
            <div className="text-[10px] text-foreground-faint mt-2">
              Amber = created during a run by the evolution engine. R = rolling reward. Plus a council of 3 judges on different models.
            </div>
          </Panel>

          <Panel title="Live events">
            <EventFeed events={events} />
          </Panel>

          <ChatBox runId={id} />
        </div>
      </div>

      {openTask && <TaskDrawer taskId={openTask} onClose={() => setOpenTask(null)} />}
    </div>
  );
}

function TaskRow({ t, onOpen }: { t: Task; onOpen: () => void }) {
  const who = t.agent_name ?? (EXECUTOR.has(t.task_type) ? "Executor (code)" : t.agent_id ? short(t.agent_id) : "waiting for an agent");
  return (
    <button onClick={onOpen} className="w-full flex items-center gap-3 text-left rounded-btn px-2 py-1.5 hover:bg-white/[0.03]">
      <Status value={t.status} className="w-24 sm:w-36 justify-center shrink-0" />
      <span className="text-sm text-foreground w-28 sm:w-44 truncate shrink-0">{t.task_type.replaceAll("_", " ")}</span>
      <span className={cn("text-xs truncate flex-1", t.agent_id || EXECUTOR.has(t.task_type) ? "text-foreground-muted" : "text-amber-highlight")}>
        {who}
      </span>
      {t.reward.reward !== null && <span className="font-mono text-[10px] text-foreground-faint">R {pct(t.reward.reward)}</span>}
      {t.error && <span className="text-[10px] text-red-300 truncate max-w-[180px]">{t.error}</span>}
    </button>
  );
}

function BriefView({ brief }: { brief?: Brief }) {
  if (!brief?.ready) return <Panel title="Research brief"><Empty>Intake is still reading the inputs.</Empty></Panel>;
  return (
    <div className="space-y-5">
      <Panel title="Research brief" action={<span className="text-xs font-mono text-cyan-highlight">domain: {brief.domain}</span>}>
        <Label>Facts detected</Label>
        <div className="space-y-1 mb-4">
          {brief.facts.map((f, i) => (
            <div key={i} className="text-xs flex gap-2">
              <span className="font-mono text-cyan-highlight w-48 shrink-0">{f.fact}</span>
              <span className="text-foreground-muted break-words">{f.evidence}</span>
            </div>
          ))}
        </div>
        <Label>Reference targets (what results are compared against, best first)</Label>
        <div className="flex flex-wrap gap-2">
          {brief.reference_targets.map((t) => (
            <span key={t.rank} className="text-xs font-mono rounded-full border border-border-subtle px-2 py-0.5">
              #{t.rank} {t.type.replaceAll("_", " ")}
            </span>
          ))}
        </div>
      </Panel>
      <Panel title="Which agents work, and why">
        <div className="space-y-1">
          {brief.activation.map((a) => (
            <div key={a.agent_id} className={cn("text-xs flex gap-2", !a.active && "opacity-50")}>
              <span className={cn("font-mono w-40 shrink-0", a.active ? "text-emerald-300" : "text-foreground-faint")}>
                {a.active ? "on" : "off"} {short(a.agent_id)}
              </span>
              <span className="text-foreground-muted">{a.reason}</span>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}

function ReportView({ runId }: { runId: string }) {
  const { data, error } = usePoll<{ markdown: string; why_differs: { ledger_entry_id: string; explanation: string }[] }>(
    `/runs/${runId}/report`,
    20000,
  );
  if (error || !data) return <Panel title="Report"><Empty>No report yet. The Reporter writes it at the end of the run.</Empty></Panel>;
  return (
    <Panel title="Report" glow="cyan">
      <Markdown text={data.markdown} />
      {data.why_differs.length > 0 && (
        <div className="mt-4">
          <Label>Why results differ (from the ledger)</Label>
          <ul className="list-disc pl-5 text-sm text-foreground-secondary space-y-1">
            {data.why_differs.map((w) => (
              <li key={w.ledger_entry_id}>{w.explanation}</li>
            ))}
          </ul>
        </div>
      )}
    </Panel>
  );
}

function LedgerView({ runId }: { runId: string }) {
  const { data } = usePoll<{ id: string; category: string; description: string }[]>(`/runs/${runId}/ledger`, 20000);
  return (
    <Panel title="Deviation ledger">
      <p className="text-xs text-foreground-muted mb-3">Every change from the paper or the official code, recorded at the moment it was made.</p>
      {!data?.length ? (
        <Empty>No deviations recorded yet.</Empty>
      ) : (
        <div className="space-y-1.5">
          {data.map((e) => (
            <div key={e.id} className="text-xs flex gap-2">
              <span className="font-mono text-amber-highlight w-44 shrink-0">{e.category.replaceAll("_", " ")}</span>
              <span className="text-foreground-secondary">{e.description}</span>
            </div>
          ))}
        </div>
      )}
    </Panel>
  );
}

function ChatBox({ runId }: { runId: string }) {
  const { data, reload } = usePoll<{ id: string; role: string; content: string }[]>(`/runs/${runId}/chat`, 20000);
  const [text, setText] = React.useState("");
  const send = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!text.trim()) return;
    await api(`/runs/${runId}/chat`, "POST", { message: text }).catch(() => undefined);
    setText("");
    reload();
  };
  return (
    <Panel title="Chat with the AI manager">
      <div className="space-y-1.5 max-h-56 overflow-y-auto mb-2">
        {!data?.length ? (
          <Empty>Ask for a change, for example "try noisy data". The Meta-Controller re-plans.</Empty>
        ) : (
          data.map((m) => (
            <div key={m.id} className={cn("text-xs rounded-btn p-2", m.role === "researcher" ? "bg-canvas-elevated ml-6" : "bg-cyan/[0.06] mr-6")}>
              <div className="font-mono text-[9px] uppercase text-foreground-faint">{m.role.replace("_", " ")}</div>
              {m.content}
            </div>
          ))
        )}
      </div>
      <form onSubmit={send} className="flex gap-2">
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Message the Meta-Controller"
          className="flex-1 h-8 px-2.5 rounded-btn bg-canvas-elevated border border-border-subtle text-xs focus:outline-none focus:border-cyan/50"
        />
        <Btn type="submit" variant="cyan">
          <Send className="w-3.5 h-3.5" />
        </Btn>
      </form>
    </Panel>
  );
}
