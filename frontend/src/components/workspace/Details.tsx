"use client";

// Detail sheets: a task (the "why": reward, council, transcript) and a laptop job (logs).

import * as React from "react";
import { ArrowSquareOut, ThumbsDown, ThumbsUp } from "@phosphor-icons/react";
import { api } from "@/lib/api";
import { usePoll } from "@/lib/hooks";
import type { Council, Message, Task, TreeNode } from "@/lib/types";
import { TIERS } from "@/lib/types";
import { cn } from "@/lib/utils";
import { compact, duration, metric, num, sentence, statusLabel, taskWho, type Job, type JobLog } from "@/lib/workspace/model";
import { Sheet } from "./Sheet";
import { Button, Empty, Pre, Skeleton, StatusBadge, json } from "./ui";

type TaskDetail = Task & { langsmith_trace_url?: string | null };

function Section({ title, children, action }: { title: string; children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <section>
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-[15px] font-semibold text-v2-text">{title}</h3>
        {action}
      </div>
      {children}
    </section>
  );
}

export function TaskSheet({ taskId, onClose }: { taskId: string; onClose: () => void }) {
  const { data: task, reload } = usePoll<TaskDetail>(`/tasks/${taskId}`, 10000);
  const { data: messages } = usePoll<Message[]>(`/tasks/${taskId}/messages`, 10000);
  const { data: council } = usePoll<Council>(task?.agent_id ? `/tasks/${taskId}/council` : null, 15000);
  const [sending, setSending] = React.useState(false);

  const feedback = async (value: "up" | "down") => {
    setSending(true);
    await api(`/tasks/${taskId}/feedback`, "POST", { value }).catch(() => undefined);
    setSending(false);
    reload();
  };

  const r = task?.reward;
  const rows: [string, string, string][] = r
    ? [
        ["Reward", num(r.reward), "What the agent's score moves by"],
        ["Outcome", num(r.outcome), "Half objective check, half council"],
        ["Objective check", num(r.outcome_det), "Did the output pass the hard checks"],
        ["Council", num(r.council_q), "Average of the three judges"],
        ["Cost", num(r.cost), "Share of the budget used"],
        ["Tokens", compact(r.tokens_in + r.tokens_out), `${duration(task?.created_at, task?.ended_at) || "-"} of work`],
      ]
    : [];

  return (
    <Sheet
      onClose={onClose}
      title={task ? sentence(task.task_type) : "Task"}
      subtitle={
        task && (
          <div className="flex flex-wrap items-center gap-2 text-[13px] text-v2-text3">
            <StatusBadge status={task.status} />
            <span>
              {taskWho(task)}
              {task.steps > 0 && `, ${task.steps} ${task.steps === 1 ? "step" : "steps"}`}
            </span>
          </div>
        )
      }
    >
      {!task ? (
        <div className="space-y-3">
          <Skeleton className="h-20" />
          <Skeleton className="h-40" />
        </div>
      ) : (
        <>
          {task.error && (
            <div className="rounded-[10px] bg-v2-red/10 text-v2-red text-[13px] px-3.5 py-3" role="alert">
              {task.error}
            </div>
          )}

          {task.agent_id && (
            <Section
              title="How it scored"
              action={
                task.langsmith_trace_url ? (
                  <a href={task.langsmith_trace_url} target="_blank" rel="noreferrer" className="text-[13px] text-v2-accent inline-flex items-center gap-1">
                    Trace in LangSmith <ArrowSquareOut size={14} />
                  </a>
                ) : undefined
              }
            >
              <dl className="grid grid-cols-2 sm:grid-cols-3 gap-px rounded-[10px] overflow-hidden bg-v2-line/[0.06]">
                {rows.map(([k, v, hint]) => (
                  <div key={k} className="bg-v2-surface px-3.5 py-3" title={hint}>
                    <dt className="text-[12px] text-v2-text3">{k}</dt>
                    <dd className="text-[19px] font-semibold text-v2-text tnum mt-0.5">{v}</dd>
                  </div>
                ))}
              </dl>
              {["done", "failed"].includes(task.status) && (
                <div className="flex items-center gap-2 mt-3 text-[13px] text-v2-text2">
                  <span>Was this useful?</span>
                  <Button
                    size="sm"
                    kind={r?.feedback === "up" ? "primary" : "secondary"}
                    disabled={sending}
                    aria-pressed={r?.feedback === "up"}
                    onClick={() => feedback("up")}
                  >
                    <ThumbsUp size={15} /> Yes
                  </Button>
                  <Button
                    size="sm"
                    kind={r?.feedback === "down" ? "destructive" : "secondary"}
                    disabled={sending}
                    aria-pressed={r?.feedback === "down"}
                    onClick={() => feedback("down")}
                  >
                    <ThumbsDown size={15} /> No
                  </Button>
                </div>
              )}
            </Section>
          )}

          {council && council.judges.length > 0 && (
            <Section title={council.split ? "Council (the judges disagreed)" : "Council"}>
              <ul className="space-y-2">
                {council.judges.map((j) => (
                  <li key={j.judge_agent_id} className="v2-card px-4 py-3">
                    <div className="flex items-baseline justify-between gap-3">
                      <span className="text-[14px] font-medium text-v2-text">{TIERS[j.tier] ?? j.tier}</span>
                      <span className="text-[17px] font-semibold tnum text-v2-text">{num(j.overall)}</span>
                    </div>
                    <p className="text-[13px] text-v2-text2 mt-1 leading-relaxed">{j.rationale}</p>
                    {Object.keys(j.scores).length > 0 && (
                      <p className="text-[12px] text-v2-text3 mt-1.5 tnum">
                        {Object.entries(j.scores)
                          .map(([k, v]) => `${sentence(k)} ${num(v)}`)
                          .join(", ")}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            </Section>
          )}

          {task.output && (
            <Section title="Output">
              <Pre>{json(task.output)}</Pre>
            </Section>
          )}

          <Section title="Transcript">
            {!messages ? (
              <Skeleton className="h-32" />
            ) : messages.length <= 1 ? (
              <p className="text-[13px] text-v2-text3">No steps yet.</p>
            ) : (
              <ol className="space-y-2">
                {messages.slice(1).map((m) => {
                  const agent = m.role === "assistant";
                  return (
                    <li key={m.seq} className={cn("rounded-[8px] px-3.5 py-2.5", agent ? "bg-v2-accent/[0.07]" : "bg-v2-raised")}>
                      <div className="text-[12px] font-medium text-v2-text3 mb-1">
                        {agent ? "Agent" : sentence(m.role)}
                        {m.tool_name ? `, ${m.tool_name}` : ""}
                      </div>
                      <div className="v2-mono text-[12px] text-v2-text2 whitespace-pre-wrap break-words max-h-48 overflow-auto v2-scroll">
                        {(m.content ?? JSON.stringify(m.tool_result ?? m.tool_args ?? "")).slice(0, 2000)}
                      </div>
                    </li>
                  );
                })}
              </ol>
            )}
          </Section>
        </>
      )}
    </Sheet>
  );
}

export function JobSheet({ job, onClose }: { job: Job; onClose: () => void }) {
  const live = ["queued", "claimed", "running"].includes(job.status);
  const { data: logs } = usePoll<JobLog[]>(`/jobs/${job.id}/logs`, live ? 4000 : 60000);
  const end = React.useRef<HTMLDivElement>(null);
  React.useEffect(() => {
    if (live) end.current?.scrollIntoView({ block: "nearest" });
  }, [logs, live]);
  const argv = Array.isArray(job.payload?.argv) ? (job.payload.argv as string[]).join(" ") : null;
  // The worker may nest the numbers ({ metrics: {...}, status }); show only numeric values, flattened.
  const numbers = Object.entries({ ...(job.metrics ?? {}), ...((job.metrics?.metrics as unknown as Record<string, unknown>) ?? {}) }).filter(
    ([, v]) => typeof v === "number",
  ) as [string, number][];

  return (
    <Sheet
      wide
      onClose={onClose}
      title={sentence(job.type)}
      subtitle={
        <div className="flex flex-wrap items-center gap-2 text-[13px] text-v2-text3">
          <StatusBadge status={job.status} />
          <span>
            {[
              job.attempt > 1 ? `attempt ${job.attempt}` : null,
              job.started_at ? duration(job.started_at, job.finished_at) : null,
              job.exit_code !== null ? `exit code ${job.exit_code}` : null,
            ]
              .filter(Boolean)
              .join(", ")}
          </span>
        </div>
      }
    >
      {job.policy_reason && <p className="text-[13px] text-v2-text3">Allowed by policy: {job.policy_reason}</p>}
      {argv && (
        <Section title="Command">
          <Pre>{argv}</Pre>
        </Section>
      )}
      {numbers.length > 0 && (
        <Section title="Metrics">
          <dl className="grid grid-cols-2 sm:grid-cols-3 gap-px rounded-[10px] overflow-hidden bg-v2-line/[0.06]">
            {numbers.map(([k, v]) => (
              <div key={k} className="bg-v2-surface px-3.5 py-3">
                <dt className="text-[12px] text-v2-text3">{k}</dt>
                <dd className="text-[17px] font-semibold tnum text-v2-text mt-0.5">{metric(v)}</dd>
              </div>
            ))}
          </dl>
        </Section>
      )}
      <Section title="Log">
        {!logs ? (
          <Skeleton className="h-40" />
        ) : !logs.length ? (
          job.stdout_tail || job.stderr_tail ? (
            <Pre className="max-h-[50vh]">{[job.stdout_tail, job.stderr_tail].filter(Boolean).join("\n")}</Pre>
          ) : (
            <Empty title={live ? "Waiting for output" : "No output"}>{live ? "Lines appear here as the laptop sends them." : undefined}</Empty>
          )
        ) : (
          <div className="v2-mono text-[12px] leading-relaxed bg-[#141B19] text-[#DCE3DF] rounded-[8px] p-3.5 max-h-[55vh] overflow-auto v2-scroll whitespace-pre-wrap break-words">
            {logs.map((l) => (
              <span key={l.seq} className={l.stream === "stderr" ? "text-[#E8A79E]" : undefined}>
                {l.chunk}
                {l.chunk.endsWith("\n") ? "" : "\n"}
              </span>
            ))}
            <div ref={end} />
          </div>
        )}
      </Section>
    </Sheet>
  );
}

export function ExperimentTree({
  roots,
  onControl,
}: {
  roots: TreeNode[];
  onControl?: (id: string, action: "pause" | "kill" | "expand") => void;
}) {
  if (!roots.length)
    return (
      <Empty title="No branches yet">The baseline appears here once the plan reaches the Executor, then each what-if branch grows from it.</Empty>
    );
  return (
    <div className="space-y-5">
      {roots.map((r) => (
        <BranchFamily key={r.id} node={r} onControl={onControl} />
      ))}
    </div>
  );
}

const BRANCH_DOT: Record<string, string> = {
  expanded: "bg-v2-accent",
  done: "bg-v2-accent",
  running: "bg-v2-accent",
  queued: "bg-v2-gold",
  proposed: "bg-v2-gold",
  pruned: "bg-v2-text3/50",
  killed: "bg-v2-text3/50",
  failed: "bg-v2-red",
};

function Metrics({ node }: { node: TreeNode }) {
  const metrics = Object.entries(node.metrics);
  if (!metrics.length) return null;
  return (
    <dl className="flex flex-wrap gap-x-5 gap-y-1.5 mt-2.5">
      {metrics.map(([k, v]) => {
        const d = node.delta_vs_baseline?.[k];
        return (
          <div key={k}>
            <dt className="v2-mono text-[12px] text-v2-text3">{k}</dt>
            <dd className="text-[14px] font-semibold tnum text-v2-text">
              {metric(v)}
              {d && d.delta !== 0 && (
                <span className={cn("ml-1.5 text-[12px] font-medium", d.beyond_seed_variance ? "text-v2-accent" : "text-v2-text3")}>
                  {d.delta > 0 ? "+" : ""}
                  {metric(d.delta)}
                  {d.beyond_seed_variance ? ", beyond seed noise" : ", within seed noise"}
                </span>
              )}
            </dd>
          </div>
        );
      })}
    </dl>
  );
}

/** A node with its children: the root reads as the origin row, children as a grid of branch cards. */
function BranchFamily({
  node,
  onControl,
}: {
  node: TreeNode;
  onControl?: (id: string, action: "pause" | "kill" | "expand") => void;
}) {
  return (
    <div>
      <div className="rounded-[8px] border border-v2-accent/20 bg-v2-accent/[0.05] px-4 py-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-[14px] font-semibold text-v2-text leading-snug">{node.hypothesis}</p>
            <p className="text-[12px] text-v2-text3 mt-0.5">
              {sentence(node.kind ?? "baseline")}
              {node.seeds.length > 0 && `, seeds ${node.seeds.join(", ")}`}
            </p>
          </div>
          <StatusBadge status={node.status} />
        </div>
        <Metrics node={node} />
      </div>
      {node.children.length > 0 && (
        <ul className="grid sm:grid-cols-2 gap-2.5 mt-2.5">
          {node.children.map((c) => (
            <BranchCard key={c.id} node={c} onControl={onControl} />
          ))}
        </ul>
      )}
    </div>
  );
}

function BranchCard({
  node,
  onControl,
}: {
  node: TreeNode;
  onControl?: (id: string, action: "pause" | "kill" | "expand") => void;
}) {
  const open = ["running", "queued", "pending", "proposed"].includes(node.status);
  const faded = ["pruned", "killed"].includes(node.status);
  return (
    <li className={cn("relative rounded-[8px] border border-v2-line/[0.09] bg-v2-surface px-4 py-3.5 flex flex-col", faded && "opacity-75")}>
      <div className="flex items-center gap-2">
        <span className={cn("w-1.5 h-1.5 rounded-full", BRANCH_DOT[node.status] ?? "bg-v2-text3/50")} aria-hidden />
        <span className="text-[12px] font-medium text-v2-text3">{statusLabel(node.status)}</span>
      </div>
      <p className="text-[14px] font-semibold text-v2-text mt-1.5 leading-snug">{node.hypothesis}</p>
      {node.seeds.length > 0 && <p className="text-[12px] text-v2-text3 mt-0.5">Seeds {node.seeds.join(", ")}</p>}
      <Metrics node={node} />
      {node.decision_reason && (
        <p className="text-[13px] text-v2-text2 mt-2.5 pt-2.5 border-t border-v2-line/[0.07]">
          <span className="font-semibold text-v2-text">Why: </span>
          {node.decision_reason}
        </p>
      )}
      {onControl && open && (
        <div className="flex gap-2 mt-3">
          <Button size="sm" onClick={() => onControl(node.id, "pause")}>
            Pause
          </Button>
          <Button size="sm" kind="destructive" onClick={() => onControl(node.id, "kill")}>
            Stop branch
          </Button>
        </div>
      )}
      {node.children.length > 0 && (
        <ul className="mt-3 space-y-2 pl-3 border-l border-v2-line/[0.1]">
          {node.children.map((c) => (
            <BranchCard key={c.id} node={c} onControl={onControl} />
          ))}
        </ul>
      )}
    </li>
  );
}
