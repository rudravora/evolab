"use client";

import * as React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { fmtTime } from "@/lib/hooks";
import type { StreamEvent, TreeNode } from "@/lib/types";
import { Empty, Status } from "./bits";

export function ExperimentTree({ roots }: { roots: TreeNode[] }) {
  if (!roots.length) return <Empty>No branches yet. The baseline appears once the plan reaches the Executor.</Empty>;
  return (
    <div className="space-y-2">
      {roots.map((r) => (
        <Node key={r.id} node={r} depth={0} />
      ))}
    </div>
  );
}

function Node({ node, depth }: { node: TreeNode; depth: number }) {
  return (
    <div style={{ marginLeft: depth * 18 }} className={depth ? "border-l border-border-subtle pl-3" : ""}>
      <div className="rounded-btn border border-border-subtle bg-canvas-elevated p-2.5">
        <div className="flex items-start justify-between gap-2">
          <div>
            <div className="text-sm text-foreground">{node.hypothesis}</div>
            <div className="text-[10px] font-mono text-foreground-faint mt-0.5">
              {node.kind} {node.seeds.length > 0 && `· seeds ${node.seeds.join(", ")}`}
            </div>
          </div>
          <Status value={node.status} />
        </div>
        {Object.keys(node.metrics).length > 0 && (
          <div className="flex flex-wrap gap-3 mt-1.5 font-mono text-[11px]">
            {Object.entries(node.metrics).map(([k, v]) => {
              const d = node.delta_vs_baseline?.[k];
              return (
                <span key={k} className="text-foreground-secondary">
                  {k} {typeof v === "number" ? v.toFixed(4) : v}
                  {d && (
                    <span className={d.delta < 0 ? "text-emerald-300" : "text-amber-highlight"}>
                      {" "}
                      ({d.delta > 0 ? "+" : ""}
                      {d.delta.toFixed(4)}
                      {d.beyond_seed_variance ? ", beyond seed variance" : ""})
                    </span>
                  )}
                </span>
              );
            })}
          </div>
        )}
        {node.decision_reason && <div className="text-xs text-foreground-muted mt-1.5">Why: {node.decision_reason}</div>}
      </div>
      {node.children.length > 0 && (
        <div className="mt-2 space-y-2">
          {node.children.map((c) => (
            <Node key={c.id} node={c} depth={depth + 1} />
          ))}
        </div>
      )}
    </div>
  );
}

const QUIET = new Set(["agent.message", "job.log"]);

function describe(e: StreamEvent): string {
  const d = e.data;
  switch (e.type) {
    case "run.status":
      return `Run is ${d.status}`;
    case "agent.task":
      return `${d.agent_name ?? "Task"}: ${d.summary ?? d.status}`;
    case "intake.brief":
      return `Research Brief ready: ${d.facts_count} facts`;
    case "agent.activation":
      return `${String(d.agent_id).replace("agt_", "")} ${d.active ? "activated" : "not needed"}: ${d.reason}`;
    case "approval.requested":
      return `Approval needed (${d.type}): ${d.summary}`;
    case "approval.decided":
      return `Approval ${d.status}`;
    case "plan.revised":
      return `Plan v${d.version} (${d.kind}, trigger ${d.trigger}): ${d.reason}`;
    case "job.status":
      return `Laptop job ${d.status}`;
    case "experiment.metrics":
      return `Experiment result: ${Object.entries(d.metrics ?? {}).map(([k, v]) => `${k}=${v}`).join(", ")}`;
    case "branch.update":
      return `Branch ${d.status}${d.decision_reason ? `: ${d.decision_reason}` : ""}`;
    case "ledger.entry":
      return `Ledger (${d.category}): ${d.description}`;
    case "memory.hit":
      return `Memory reused (${d.source} ${d.kind})`;
    case "memory.write":
      return `Lesson saved to memory (${d.kind})`;
    case "council.score":
      return `Council scored a task: Q=${d.q ?? "pending"}${d.split ? " (split)" : ""}`;
    case "agent.score":
      return `Reward ${d.reward} for ${String(d.agent_id).replace("agt_", "")}`;
    case "agent.evolution":
      return `EVOLUTION: ${d.action}${d.ladder_step ? ` (${d.ladder_step})` : ""}: ${d.reason}`;
    case "capability.gap":
      return `Capability gap: needs ${(d.required_tags ?? []).join(", ")} (${d.source})`;
    case "report.ready":
      return "Report ready";
    case "budget.warning":
      return `Budget warning: ${d.metric} at ${d.used} of ${d.limit}`;
    case "chat.message":
      return `${d.role}: ${d.content}`;
    case "worker.status":
      return `Worker ${d.status}`;
    default:
      return e.type;
  }
}

const TONE: Record<string, string> = {
  "agent.evolution": "text-amber-highlight",
  "capability.gap": "text-amber-highlight",
  "approval.requested": "text-amber-highlight",
  "report.ready": "text-emerald-300",
  "memory.write": "text-emerald-300",
  "memory.hit": "text-emerald-300",
  "run.status": "text-cyan-highlight",
  "plan.revised": "text-cyan-highlight",
};

export function EventFeed({ events, verbose }: { events: StreamEvent[]; verbose?: boolean }) {
  const shown = events.filter((e) => verbose || !QUIET.has(e.type)).slice(-120).reverse();
  if (!shown.length) return <Empty>Waiting for events...</Empty>;
  return (
    <div className="space-y-1 max-h-[420px] overflow-y-auto pr-1">
      {shown.map((e) => (
        <div key={`${e.id}-${e.type}`} className="text-xs flex gap-2">
          <span className="font-mono text-[10px] text-foreground-faint shrink-0 w-14">#{e.id}</span>
          <span className={TONE[e.type] ?? "text-foreground-secondary"}>{describe(e)}</span>
        </div>
      ))}
    </div>
  );
}

export function Markdown({ text }: { text: string }) {
  return (
    <div className="prose-evolab text-sm text-foreground-secondary leading-relaxed space-y-2 [&_h1]:text-xl [&_h1]:font-semibold [&_h1]:text-foreground [&_h2]:text-base [&_h2]:font-semibold [&_h2]:text-foreground [&_h2]:mt-4 [&_table]:text-xs [&_td]:border [&_td]:border-border-subtle [&_td]:px-2 [&_td]:py-1 [&_th]:border [&_th]:border-border-subtle [&_th]:px-2 [&_th]:py-1 [&_ul]:list-disc [&_ul]:pl-5 [&_code]:font-mono [&_code]:text-cyan-highlight">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
    </div>
  );
}

export { fmtTime };
