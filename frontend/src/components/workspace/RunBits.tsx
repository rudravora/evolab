"use client";

import * as React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { StreamEvent, Task } from "@/lib/types";
import { cn } from "@/lib/utils";
import { agentShort, hhmm, isLive, metric, sentence, statusLabel, toneOf, type Tone } from "@/lib/workspace/model";
import { TONE_FILL } from "./ui";

/**
 * The run strip: the approved plan as a row of segments, one per task, in plan order.
 * It is the one place the design spends its boldness, because the plan is what the
 * researcher approved and what they are watching.
 */
export function RunStrip({
  tasks,
  onOpen,
  size = "md",
  onDark = false,
  className,
}: {
  tasks: Task[];
  onOpen?: (id: string) => void;
  size?: "sm" | "md";
  /** On the dark ink card: waiting segments need a light track, finished ones the light accent. */
  onDark?: boolean;
  className?: string;
}) {
  const waitingFill = onDark ? "bg-white/15" : "bg-v2-line/[0.1]";
  if (!tasks.length) {
    return <div className={cn("rounded-full", waitingFill, size === "sm" ? "h-1.5" : "h-2.5", className)} aria-hidden />;
  }
  const done = tasks.filter((t) => ["done", "skipped"].includes(t.status)).length;
  return (
    <div className={className}>
      <ol
        aria-label={`Plan progress: ${done} of ${tasks.length} tasks finished`}
        className={cn("flex gap-[3px]", size === "sm" ? "h-1.5" : "h-2.5")}
      >
        {tasks.map((t) => {
          const tone: Tone = t.status === "skipped" ? "neutral" : toneOf(t.status);
          const label = `${sentence(t.task_type)}: ${statusLabel(t.status)}`;
          const cls = cn(
            "flex-1 rounded-full transition-colors",
            ["pending", "blocked", "queued"].includes(t.status) ? waitingFill : onDark && ["green", "accent"].includes(tone) ? "bg-[#88C3AA]" : TONE_FILL[tone],
            isLive(t.status) && "v2-pulse",
          );
          return (
            <li key={t.id} className="flex-1 flex" title={label}>
              {onOpen ? (
                <button onClick={() => onOpen(t.id)} aria-label={label} className={cn(cls, "hover:brightness-125")} />
              ) : (
                <span className={cls} aria-label={label} />
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}

export function Markdown({ text }: { text: string }) {
  return (
    <div className="v2-prose">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
    </div>
  );
}

const QUIET = new Set(["agent.message", "job.log", "worker.status"]);
// Intermediate states that would otherwise flood the feed; the Jobs and Experiments tabs show them.
const QUIET_STATUS: Record<string, Set<string>> = {
  "job.status": new Set(["pending", "queued", "claimed"]),
  "branch.update": new Set(["proposed", "queued"]),
};

function quiet(e: StreamEvent) {
  return QUIET.has(e.type) || !!QUIET_STATUS[e.type]?.has(String(e.data.status));
}

type Line = { text: string; tone?: Tone; strong?: boolean };

/** Plain-language line for one stream event (docs/API.md section 6). `names` maps agent ids to names. */
/** Events that change what the researcher should know: decisions, results, deviations. */
export const KEY_EVENTS = [
  "run.status",
  "intake.brief",
  "approval.requested",
  "approval.decided",
  "plan.revised",
  "agent.evolution",
  "agent.probation",
  "capability.gap",
  "experiment.metrics",
  "branch.update",
  "ledger.entry",
  "memory.write",
  "memory.hit",
  "job.requeued",
  "budget.warning",
  "report.ready",
];

export function describeEvent(e: StreamEvent, names: Record<string, string> = {}): Line {
  const d = e.data;
  const who = (id: unknown) => names[String(id)] ?? agentShort(String(id ?? ""));
  switch (e.type) {
    case "run.status":
      return { text: `Run is now ${statusLabel(String(d.status)).toLowerCase()}`, tone: toneOf(String(d.status)), strong: true };
    case "agent.task": {
      const name = d.agent_name ?? (d.agent_id ? who(d.agent_id) : "A task");
      const summary = typeof d.summary === "string" ? d.summary.replace(new RegExp(`^${String(name).replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\s*`), "") : "";
      return { text: summary ? `${name}: ${summary}` : `${name} is ${statusLabel(String(d.status)).toLowerCase()}` };
    }
    case "intake.brief":
      return { text: `Research brief ready with ${d.facts_count} facts`, tone: "accent" };
    case "agent.activation":
      return { text: `${who(d.agent_id)} ${d.active ? "joins the team" : "is not needed"}: ${d.reason}` };
    case "approval.requested":
      return { text: `Needs your approval: ${d.summary ?? sentence(String(d.type))}`, tone: "orange", strong: true };
    case "approval.decided":
      return {
        text: d.status === "approved" ? "You approved the request" : d.status === "rejected" ? "You rejected the request" : `Request ${String(d.status)}`,
        tone: toneOf(String(d.status)),
      };
    case "plan.revised":
      return { text: `Plan revised to v${d.version}: ${d.reason}`, tone: "accent" };
    case "job.status":
      return { text: `Laptop job ${statusLabel(String(d.status)).toLowerCase()}`, tone: toneOf(String(d.status)) };
    case "job.requeued":
      return { text: `Laptop job retried (attempt ${d.attempt}): ${d.reason}`, tone: "orange" };
    case "experiment.metrics":
      return {
        text: `Result: ${Object.entries(d.metrics ?? {})
          .map(([k, v]) => `${k} ${metric(v)}`)
          .join(", ")}`,
        tone: "green",
      };
    case "branch.update":
      return { text: `Branch ${statusLabel(String(d.status)).toLowerCase()}${d.decision_reason ? `: ${d.decision_reason}` : ""}` };
    case "ledger.entry":
      return { text: `Deviation recorded: ${d.description}` };
    case "memory.hit":
      return { text: `Reused a ${d.source} lesson from memory`, tone: "green" };
    case "memory.write":
      return { text: "Saved a verified lesson to memory", tone: "green" };
    case "council.score":
      return { text: `Council scored a task${d.q != null ? ` at ${Number(d.q).toFixed(2)}` : ""}${d.split ? " (judges split)" : ""}` };
    case "agent.score":
      return { text: `${who(d.agent_id)} earned reward ${Number(d.reward).toFixed(2)}` };
    case "agent.evolution":
      return { text: `Evolution: ${sentence(String(d.action))}${d.reason ? `. ${d.reason}` : ""}`, tone: "purple", strong: true };
    case "agent.probation":
      return { text: `${who(d.agent_id)} probation ${d.result ?? d.status ?? "updated"}`, tone: "purple" };
    case "capability.gap":
      return { text: `Missing skill: ${(d.required_tags ?? []).join(", ")}`, tone: "orange" };
    case "candidates.ready":
      return { text: "Candidate papers found", tone: "accent" };
    case "report.ready":
      return { text: "Report is ready", tone: "green", strong: true };
    case "budget.warning":
      return { text: `Budget: ${d.metric} at ${d.used} of ${d.limit}`, tone: "orange" };
    case "chat.message":
      return { text: `${sentence(String(d.role))}: ${d.content}` };
    default:
      return { text: sentence(e.type.replace(".", " ")) };
  }
}

const TEXT_TONE: Record<Tone, string> = {
  accent: "text-v2-accent",
  green: "text-v2-green",
  orange: "text-v2-orange",
  red: "text-v2-red",
  purple: "text-v2-purple",
  neutral: "text-v2-text2",
};

/** Event timeline: a dot per event on a thin rail, newest first. Colour sits on the dot; only
 *  the events that matter most (decisions, evolution, run status) are set in their colour. */
export function Activity({
  events,
  names,
  limit = 80,
  maxHeight = "max-h-[460px]",
  only,
}: {
  events: StreamEvent[];
  names?: Record<string, string>;
  limit?: number;
  maxHeight?: string;
  /** Keep only these event types (a summary view); otherwise everything except log noise. */
  only?: string[];
}) {
  const shown = events
    .filter((e) => !quiet(e) && (!only || only.includes(e.type)))
    .slice(-limit)
    .reverse();
  if (!shown.length) return <p className="text-[13px] text-v2-text3 py-6 text-center">Waiting for the first event.</p>;
  return (
    <ol className={cn("overflow-y-auto v2-scroll pr-1", maxHeight)} aria-live="polite" aria-relevant="additions">
      {shown.map((e, i) => {
        const line = describeEvent(e, names);
        const at = typeof e.data.ts === "string" ? e.data.ts : typeof e.data.at === "string" ? e.data.at : null;
        return (
          <li key={`${e.id}-${e.type}`} className="relative flex gap-3 pb-3 text-[13px] leading-snug">
            {i < shown.length - 1 && <span className="absolute left-[3px] top-[14px] bottom-0 w-px bg-v2-line/[0.1]" aria-hidden />}
            <span
              className={cn("relative mt-[5px] w-[7px] h-[7px] rounded-full shrink-0 ring-[3px] ring-v2-surface", line.tone ? TONE_FILL[line.tone] : "bg-v2-text3/45")}
              aria-hidden
            />
            <span className={cn("flex-1 min-w-0 break-words", line.strong && line.tone ? `${TEXT_TONE[line.tone]} font-semibold` : "text-v2-text2")}>
              {line.text}
            </span>
            {at && <time className="v2-mono text-[12px] text-v2-text3 shrink-0">{hhmm(at)}</time>}
          </li>
        );
      })}
    </ol>
  );
}
