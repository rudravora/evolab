"use client";

// One pending decision (POST /approvals/{id}/decide), in the workspace's gold decision card.
// The summary and the two actions come first; the detail sits underneath.

import * as React from "react";
import { ArrowRight, Dna, GitBranch, ListChecks, Question, ShieldWarning } from "@phosphor-icons/react";
import { api, ApiError } from "@/lib/api";
import type { Approval as ApprovalT } from "@/lib/types";
import { TIERS } from "@/lib/types";
import { cn } from "@/lib/utils";
import { agentShort, EXECUTOR_TASKS, sentence } from "@/lib/workspace/model";
import { Button, Pre, TextArea, json } from "./ui";

const KIND: Record<string, { label: string; icon: React.ElementType }> = {
  plan: { label: "Plan approval", icon: ListChecks },
  evolution: { label: "Evolution proposal", icon: Dna },
  candidate_selection: { label: "Choose a paper", icon: GitBranch },
  human_input: { label: "An agent has a question", icon: Question },
  risky_command: { label: "Risky command", icon: ShieldWarning },
  new_package: { label: "New package", icon: ShieldWarning },
  expensive_run: { label: "Long run", icon: ShieldWarning },
};

type PlanTask = { task_id: string; task_type: string; agent_id: string | null; depends_on: string[] };

export function Approval({ approval, onDone }: { approval: ApprovalT; onDone: () => void }) {
  const [busy, setBusy] = React.useState<null | "approve" | "reject" | "edit">(null);
  const [noting, setNoting] = React.useState(false);
  const [comment, setComment] = React.useState("");
  const [err, setErr] = React.useState<string | null>(null);
  const p = approval.payload;
  const meta = KIND[approval.type] ?? { label: sentence(approval.type), icon: ShieldWarning };
  const Icon = meta.icon;
  const isQuestion = approval.type === "human_input";
  const evo = approval.type === "evolution";
  const noteId = React.useId();

  const decide = async (decision: "approve" | "reject" | "edit", edited?: object) => {
    setBusy(decision);
    setErr(null);
    try {
      await api(`/approvals/${approval.id}/decide`, "POST", { decision, comment: comment.trim() || undefined, edited_payload: edited });
      onDone();
    } catch (e) {
      setErr(e instanceof ApiError ? `${e.message}. Try again.` : "The decision did not reach the backend. Try again.");
    } finally {
      setBusy(null);
    }
  };

  const tasks = (p.plan?.tasks ?? []) as PlanTask[];

  return (
    <article
      aria-label={meta.label}
      className={cn("rounded-[10px] border", evo ? "border-v2-purple/25 bg-v2-purple/[0.05]" : "border-v2-gold/30 bg-v2-gold/[0.07]")}
    >
      <div className="flex flex-col sm:flex-row sm:items-start gap-4 px-5 py-[18px]">
        <span
          className={cn(
            "w-9 h-9 rounded-[8px] flex items-center justify-center shrink-0",
            evo ? "bg-v2-purple/[0.12] text-v2-purple" : "bg-v2-gold/[0.16] text-v2-orange",
          )}
          aria-hidden
        >
          <Icon size={19} weight="duotone" />
        </span>
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-[15px] font-semibold text-v2-text">{meta.label}</h3>
            <span className={cn("text-[12px] font-medium px-2 py-0.5 rounded-full", evo ? "bg-v2-purple/[0.12] text-v2-purple" : "bg-v2-gold/[0.18] text-v2-orange")}>
              Needs your decision
            </span>
          </div>
          <p className="text-[14px] text-v2-text2 mt-1.5 leading-relaxed">{isQuestion ? p.question ?? p.summary : p.summary}</p>
          {approval.type === "plan" && p.plan?.gaps?.length > 0 && (
            <p className="text-[13px] text-v2-orange mt-2">
              Missing {p.plan.gaps.length === 1 ? "skill" : "skills"}: {p.plan.gaps.map((g: { required_tags: string[] }) => g.required_tags.join(", ")).join("; ")}. The
              evolution engine will propose an agent.
            </p>
          )}
        </div>
        {approval.type !== "candidate_selection" && (
          <div className="flex sm:flex-col gap-2 sm:min-w-[150px]">
            <Button kind="primary" disabled={!!busy} onClick={() => decide("approve")} className="flex-1 sm:flex-none">
              {busy === "approve" ? "Approving" : isQuestion ? "Yes" : evo ? "Approve change" : "Approve plan"} <ArrowRight size={15} />
            </Button>
            <Button disabled={!!busy} onClick={() => (isQuestion ? decide("reject") : setNoting((v) => !v))} className="flex-1 sm:flex-none" aria-expanded={isQuestion ? undefined : noting}>
              {isQuestion ? (busy === "reject" ? "Sending" : "No") : "Request changes"}
            </Button>
          </div>
        )}
      </div>

      {noting && (
        <div className="px-5 pb-[18px] sm:pl-[72px]">
          <label htmlFor={noteId} className="block text-[13px] font-semibold text-v2-text2 mb-1.5">
            What should change?
          </label>
          <TextArea
            id={noteId}
            rows={2}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="For example: skip the noise branch, use 3 seeds instead of 5"
          />
          <div className="flex gap-2 mt-2">
            <Button kind="destructive" size="sm" disabled={!!busy} onClick={() => decide("reject")}>
              {busy === "reject" ? "Sending" : "Send back to the AI manager"}
            </Button>
            <Button size="sm" kind="plain" onClick={() => setNoting(false)}>
              Cancel
            </Button>
          </div>
        </div>
      )}

      {err && (
        <p className="px-5 pb-4 sm:pl-[72px] text-[13px] text-v2-red" role="alert">
          {err}
        </p>
      )}

      {/* Detail */}
      <div className="px-5 pb-[18px] sm:pl-[72px] space-y-3 text-[13px]">
        {approval.type === "plan" && tasks.length > 0 && (
          <details>
            <summary className="cursor-pointer text-v2-accent font-semibold">Show the {tasks.length} tasks</summary>
            <ol className="mt-2.5 rounded-[8px] bg-v2-surface border border-v2-line/[0.08] divide-y divide-v2-line/[0.06]">
              {tasks.map((t, i) => {
                const gap = !t.agent_id && !EXECUTOR_TASKS.has(t.task_type);
                return (
                  <li key={t.task_id} className="flex items-center gap-3 px-3 py-2">
                    <span className="v2-mono w-5 text-[12px] text-v2-text3 text-right shrink-0">{String(i + 1).padStart(2, "0")}</span>
                    <span className="flex-1 min-w-0 truncate text-v2-text">{sentence(t.task_type)}</span>
                    <span className={cn("truncate max-w-[45%] text-right", gap ? "text-v2-orange font-semibold" : "text-v2-text3")}>
                      {t.agent_id ? agentShort(t.agent_id) : EXECUTOR_TASKS.has(t.task_type) ? "Executor" : "Missing skill"}
                    </span>
                  </li>
                );
              })}
            </ol>
          </details>
        )}
        {approval.type === "plan" && p.diff && (
          <details>
            <summary className="cursor-pointer text-v2-accent font-semibold">Show the proposed change</summary>
            <div className="mt-2 space-y-2">
              {p.reason && <p className="text-v2-text2">{p.reason}</p>}
              <Pre>{json(p.diff)}</Pre>
            </div>
          </details>
        )}

        {evo && (
          <div className="space-y-3">
            {p.proposed_agent && (
              <div className="rounded-[8px] bg-v2-surface border border-v2-line/[0.08] px-3.5 py-3">
                <div className="text-[14px] font-semibold text-v2-text">{p.proposed_agent.name}</div>
                <dl className="mt-1.5 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-v2-text2">
                  {p.action && (
                    <>
                      <dt className="text-v2-text3">Change</dt>
                      <dd>
                        {sentence(p.action)}
                        {p.ladder_step ? `, ${sentence(p.ladder_step).toLowerCase()}` : ""}
                      </dd>
                    </>
                  )}
                  {p.proposed_agent.model && (
                    <>
                      <dt className="text-v2-text3">Model</dt>
                      <dd>{TIERS[p.proposed_agent.model] ?? p.proposed_agent.model}</dd>
                    </>
                  )}
                  {p.proposed_agent.capability_tags && (
                    <>
                      <dt className="text-v2-text3">Skills</dt>
                      <dd className="v2-mono text-[12px]">{p.proposed_agent.capability_tags.join(", ")}</dd>
                    </>
                  )}
                  {p.proposed_agent.tools && (
                    <>
                      <dt className="text-v2-text3">Tools</dt>
                      <dd className="v2-mono text-[12px]">{p.proposed_agent.tools.join(", ")}</dd>
                    </>
                  )}
                </dl>
              </div>
            )}
            {p.expected_effect && <p className="text-v2-text2">Expected effect: {p.expected_effect}</p>}
            {p.evidence?.length > 0 && (
              <ul className="list-disc pl-5 text-v2-text2 space-y-0.5">
                {p.evidence.map((e: string, i: number) => (
                  <li key={i}>{e}</li>
                ))}
              </ul>
            )}
            {(p.prompt_diff || p.proposed_agent?.prompt) && (
              <details>
                <summary className="cursor-pointer text-v2-accent font-semibold">{p.prompt_diff ? "Show the instruction changes" : "Show the instructions"}</summary>
                <Pre className="mt-2">
                  {p.prompt_diff
                    ? String(p.prompt_diff)
                        .split("\n")
                        .map((line: string, i: number) => (
                          <span key={i} className={line.startsWith("+") ? "text-v2-green" : line.startsWith("-") ? "text-v2-red" : ""}>
                            {line}
                            {"\n"}
                          </span>
                        ))
                    : json(p.proposed_agent.prompt)}
                </Pre>
              </details>
            )}
            {p.probation_tasks && (
              <p className="text-v2-text3">
                If you approve, it starts on probation for {p.probation_tasks} tasks. If it scores worse than what it replaces, it is rolled back automatically.
              </p>
            )}
          </div>
        )}

        {approval.type === "candidate_selection" && (
          <ul className="space-y-2">
            {(p.candidates ?? []).map((c: { title: string; url: string; why: string }, i: number) => (
              <li key={i} className="flex items-start gap-3 rounded-[8px] bg-v2-surface border border-v2-line/[0.08] px-3.5 py-3">
                <div className="flex-1 min-w-0">
                  <a href={c.url} target="_blank" rel="noreferrer" className="text-[14px] font-semibold text-v2-text hover:text-v2-accent">
                    {c.title}
                  </a>
                  <p className="text-v2-text2 mt-0.5">{c.why}</p>
                </div>
                <Button kind="primary" size="sm" disabled={!!busy} onClick={() => decide("edit", { chosen: i })}>
                  Use this paper
                </Button>
              </li>
            ))}
          </ul>
        )}

        {["risky_command", "new_package", "expensive_run"].includes(approval.type) && (
          <div className="space-y-2">
            {p.reason && <p className="text-v2-text2">{p.reason}</p>}
            <Pre>{json(p.payload ?? p, 1200)}</Pre>
          </div>
        )}
      </div>
    </article>
  );
}
