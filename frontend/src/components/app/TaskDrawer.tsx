"use client";

import * as React from "react";
import { ThumbsDown, ThumbsUp, X } from "lucide-react";
import { api } from "@/lib/api";
import { pct, usePoll } from "@/lib/hooks";
import type { Council, Message, Task } from "@/lib/types";
import { TIERS } from "@/lib/types";
import { Btn, Json, Label, Status } from "./bits";

export function TaskDrawer({ taskId, onClose }: { taskId: string; onClose: () => void }) {
  const { data: task, reload } = usePoll<Task>(`/tasks/${taskId}`, 10000);
  const { data: messages } = usePoll<Message[]>(`/tasks/${taskId}/messages`, 10000);
  const { data: council } = usePoll<Council>(task?.agent_id ? `/tasks/${taskId}/council` : null, 15000);

  const feedback = async (value: "up" | "down") => {
    await api(`/tasks/${taskId}/feedback`, "POST", { value });
    reload();
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end" onClick={onClose}>
      <div className="absolute inset-0 bg-black/50" />
      <aside
        className="relative w-full max-w-2xl h-full overflow-y-auto bg-canvas-subtle border-l border-border-medium p-5 space-y-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3">
          <div>
            <Label>{task?.agent_name ?? "Task"}</Label>
            <h3 className="text-lg font-semibold tracking-tight">{task?.task_type?.replaceAll("_", " ")}</h3>
            <div className="mt-1 flex items-center gap-2">
              {task && <Status value={task.status} />}
              {task && <span className="text-xs text-foreground-faint font-mono">{task.steps} steps</span>}
            </div>
          </div>
          <Btn variant="ghost" onClick={onClose}>
            <X className="w-4 h-4" />
          </Btn>
        </div>

        {task?.error && <div className="text-xs text-red-300 bg-red-500/10 border border-red-500/25 rounded-btn p-2.5">{task.error}</div>}

        {task?.agent_id && (
          <section className="grid grid-cols-3 gap-2 text-center">
            {[
              ["Reward", task.reward.reward],
              ["Outcome (blended)", task.reward.outcome],
              ["Objective check", task.reward.outcome_det],
              ["Council Q", task.reward.council_q],
              ["Cost", task.reward.cost],
              ["Tokens", task.reward.tokens_in + task.reward.tokens_out],
            ].map(([k, v]) => (
              <div key={String(k)} className="rounded-btn bg-canvas-elevated border border-border-subtle p-2">
                <div className="font-mono text-[9px] uppercase tracking-wider text-foreground-faint">{k}</div>
                <div className="font-mono text-sm text-foreground">{typeof v === "number" && v < 2 ? pct(v) : String(v ?? "-")}</div>
              </div>
            ))}
          </section>
        )}
        {task?.agent_id && ["done", "failed"].includes(task.status) && (
          <div className="flex items-center gap-2 text-xs text-foreground-muted">
            Researcher feedback:
            <Btn variant={task.reward.feedback === "up" ? "cyan" : "secondary"} onClick={() => feedback("up")}>
              <ThumbsUp className="w-3.5 h-3.5" />
            </Btn>
            <Btn variant={task.reward.feedback === "down" ? "danger" : "secondary"} onClick={() => feedback("down")}>
              <ThumbsDown className="w-3.5 h-3.5" />
            </Btn>
          </div>
        )}

        {council && council.judges.length > 0 && (
          <section>
            <Label>
              Performance council ({council.status}
              {council.split ? ", split decision" : ""})
            </Label>
            <div className="space-y-2">
              {council.judges.map((j) => (
                <div key={j.judge_agent_id} className="rounded-btn border border-border-subtle bg-canvas-elevated p-2.5 text-xs">
                  <div className="flex justify-between">
                    <span className="text-foreground">{TIERS[j.tier] ?? j.tier}</span>
                    <span className="font-mono text-cyan-highlight">{pct(j.overall)}</span>
                  </div>
                  <div className="text-foreground-muted mt-1">{j.rationale}</div>
                  <div className="flex flex-wrap gap-x-3 gap-y-0.5 mt-1.5 font-mono text-[10px] text-foreground-faint">
                    {Object.entries(j.scores).map(([k, v]) => (
                      <span key={k}>
                        {k.replaceAll("_", " ")} {pct(v)}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        {task?.output && (
          <details open>
            <summary className="cursor-pointer font-mono text-[10px] uppercase tracking-[0.18em] text-foreground-faint mb-1">Output</summary>
            <Json value={task.output} />
          </details>
        )}

        <section>
          <Label>Transcript: every step the agent took</Label>
          <div className="space-y-1.5">
            {(messages ?? []).slice(1).map((m) => (
              <div
                key={m.seq}
                className={
                  m.role === "assistant"
                    ? "rounded-btn border border-cyan/20 bg-cyan/[0.04] p-2"
                    : "rounded-btn border border-border-subtle bg-canvas-elevated p-2"
                }
              >
                <div className="font-mono text-[9px] uppercase tracking-wider text-foreground-faint">
                  {m.role === "assistant" ? "agent" : m.role}
                  {m.tool_name ? ` · ${m.tool_name}` : ""}
                </div>
                <div className="text-[11px] font-mono text-foreground-secondary whitespace-pre-wrap break-words max-h-40 overflow-auto">
                  {(m.content ?? JSON.stringify(m.tool_result ?? m.tool_args ?? "")).slice(0, 1500)}
                </div>
              </div>
            ))}
          </div>
        </section>
      </aside>
    </div>
  );
}
