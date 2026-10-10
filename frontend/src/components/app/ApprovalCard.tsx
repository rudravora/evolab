"use client";

import * as React from "react";
import { Check, Dna, GitBranch, HelpCircle, ListChecks, ShieldAlert, X } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { Approval } from "@/lib/types";
import { TIERS } from "@/lib/types";
import { Btn, Json, Label, Status, short } from "./bits";

const TITLES: Record<string, { label: string; icon: React.ElementType }> = {
  plan: { label: "Plan approval", icon: ListChecks },
  evolution: { label: "Evolution proposal", icon: Dna },
  candidate_selection: { label: "Pick a paper", icon: GitBranch },
  human_input: { label: "An agent asks", icon: HelpCircle },
  risky_command: { label: "Risky command", icon: ShieldAlert },
  new_package: { label: "New package", icon: ShieldAlert },
  expensive_run: { label: "Long run", icon: ShieldAlert },
};

export function ApprovalCard({ approval, onDone }: { approval: Approval; onDone: () => void }) {
  const [busy, setBusy] = React.useState(false);
  const [comment, setComment] = React.useState("");
  const [err, setErr] = React.useState<string | null>(null);
  const p = approval.payload;
  const meta = TITLES[approval.type] ?? { label: approval.type, icon: ShieldAlert };
  const Icon = meta.icon;

  const decide = async (decision: "approve" | "reject" | "edit", edited?: object) => {
    setBusy(true);
    setErr(null);
    try {
      await api(`/approvals/${approval.id}/decide`, "POST", {
        decision,
        comment: comment || undefined,
        edited_payload: edited,
      });
      onDone();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-card border border-amber/40 bg-amber/[0.04] shadow-glow-amber p-4 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-2.5">
          <Icon className="w-4 h-4 text-amber-highlight mt-0.5 shrink-0" />
          <div>
            <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-amber-highlight">{meta.label}</div>
            <div className="text-sm text-foreground mt-0.5">{p.summary}</div>
          </div>
        </div>
        <Status value={approval.status} />
      </div>

      {approval.type === "plan" && p.plan && (
        <div className="space-y-2">
          <div className="grid gap-1">
            {(p.plan.tasks as { task_id: string; task_type: string; agent_id: string | null; depends_on: string[] }[]).map((t) => (
              <div key={t.task_id} className="flex items-center gap-2 text-xs">
                <span className="font-mono text-foreground-secondary w-44 truncate">{t.task_id}</span>
                <span className={t.agent_id ? "text-foreground-muted" : "text-amber-highlight"}>
                  {t.agent_id ? short(t.agent_id) : ["run_baseline", "run_branches"].includes(t.task_type) ? "Executor (code)" : "capability gap"}
                </span>
                {t.depends_on.length > 0 && (
                  <span className="text-foreground-faint hidden md:inline">after {t.depends_on.join(", ")}</span>
                )}
              </div>
            ))}
          </div>
          {p.plan.gaps?.length > 0 && (
            <div className="text-xs text-amber-highlight">
              Capability gaps: {p.plan.gaps.map((g: { required_tags: string[] }) => g.required_tags.join(", ")).join("; ")}. The
              resolution ladder will propose an agent.
            </div>
          )}
        </div>
      )}
      {approval.type === "plan" && p.diff && (
        <div>
          <Label>Proposed change (trigger: {p.trigger})</Label>
          <Json value={p.diff} />
          {p.reason && <div className="text-xs text-foreground-muted mt-1.5">{p.reason}</div>}
        </div>
      )}

      {approval.type === "evolution" && (
        <div className="space-y-2 text-xs">
          <div className="flex flex-wrap gap-2">
            {p.action && <Status value={p.action} />}
            {p.ladder_step && <Status value={p.ladder_step} />}
            {p.lineage && <span className="text-foreground-muted">lineage: {p.lineage}</span>}
            {p.gap?.required_tags && <span className="text-foreground-muted">needs: {p.gap.required_tags.join(", ")}</span>}
          </div>
          {p.proposed_agent && (
            <div className="rounded-btn border border-border-subtle bg-canvas-subtle p-2.5 space-y-1">
              <div className="text-foreground font-medium">{p.proposed_agent.name}</div>
              {p.proposed_agent.model && <div className="text-foreground-muted">model: {TIERS[p.proposed_agent.model] ?? p.proposed_agent.model}</div>}
              {p.proposed_agent.capability_tags && (
                <div className="text-foreground-muted">tags: {p.proposed_agent.capability_tags.join(", ")}</div>
              )}
              {p.proposed_agent.tools && <div className="text-foreground-muted">tools: {p.proposed_agent.tools.join(", ")}</div>}
              {p.proposed_agent.prompt && (
                <details>
                  <summary className="cursor-pointer text-cyan-highlight">instructions</summary>
                  <Json value={p.proposed_agent.prompt} />
                </details>
              )}
            </div>
          )}
          {p.evidence?.length > 0 && (
            <div>
              <Label>Evidence</Label>
              <ul className="list-disc pl-4 text-foreground-muted space-y-0.5">
                {p.evidence.map((e: string, i: number) => (
                  <li key={i}>{e}</li>
                ))}
              </ul>
            </div>
          )}
          {p.expected_effect && <div className="text-foreground-muted">Expected effect: {p.expected_effect}</div>}
          {p.prompt_diff && (
            <div>
              <Label>Prompt diff</Label>
              <pre className="text-[11px] font-mono bg-canvas-subtle border border-border-subtle rounded-btn p-2.5 overflow-auto max-h-64">
                {String(p.prompt_diff)
                  .split("\n")
                  .map((line, i) => (
                    <div key={i} className={line.startsWith("+") ? "text-emerald-300" : line.startsWith("-") ? "text-red-300" : "text-foreground-faint"}>
                      {line}
                    </div>
                  ))}
              </pre>
            </div>
          )}
          {p.probation_tasks && (
            <div className="text-foreground-faint">If approved, it must beat what it replaces over its next {p.probation_tasks} tasks or it is rolled back.</div>
          )}
        </div>
      )}

      {approval.type === "candidate_selection" && (
        <div className="space-y-1.5">
          {(p.candidates ?? []).map((c: { title: string; url: string; why: string }, i: number) => (
            <div key={i} className="flex items-start justify-between gap-3 rounded-btn border border-border-subtle bg-canvas-subtle p-2.5">
              <div className="text-xs">
                <a href={c.url} target="_blank" rel="noreferrer" className="text-foreground hover:text-cyan-highlight">
                  {c.title}
                </a>
                <div className="text-foreground-muted mt-0.5">{c.why}</div>
              </div>
              <Btn variant="cyan" disabled={busy} onClick={() => decide("edit", { chosen: i })}>
                Pick
              </Btn>
            </div>
          ))}
        </div>
      )}

      {approval.type === "human_input" && <div className="text-sm text-foreground-secondary">{p.question}</div>}

      {["risky_command", "new_package", "expensive_run"].includes(approval.type) && (
        <div className="text-xs space-y-1">
          <div className="text-foreground-muted">{p.reason}</div>
          <Json value={p.payload ?? p} max={1200} />
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2 pt-1">
        <input
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          placeholder={approval.type === "human_input" ? "Your answer" : "Comment (optional, sent to the AI manager on reject)"}
          className="flex-1 min-w-[180px] h-8 px-2.5 rounded-btn bg-canvas-elevated border border-border-subtle text-xs focus:outline-none focus:border-cyan/50"
        />
        {approval.type !== "candidate_selection" && (
          <Btn variant="cyan" disabled={busy} onClick={() => decide("approve")}>
            <Check className="w-3.5 h-3.5" /> {approval.type === "human_input" ? "Yes" : "Approve"}
          </Btn>
        )}
        <Btn variant="danger" disabled={busy} onClick={() => decide("reject")}>
          <X className="w-3.5 h-3.5" /> {approval.type === "human_input" ? "No" : "Reject"}
        </Btn>
      </div>
      {err && <div className="text-xs text-red-300">{err}</div>}
    </div>
  );
}
