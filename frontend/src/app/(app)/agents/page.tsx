"use client";

import * as React from "react";
import { pct, usePoll } from "@/lib/hooks";
import type { Agent } from "@/lib/types";
import { TIERS } from "@/lib/types";
import { Json, Label, Panel, Status } from "@/components/app/bits";
import { cn } from "@/lib/utils";

interface Version {
  version: number;
  model: string;
  reason: string | null;
  created_at: string;
  system_prompt?: string;
}

export default function AgentsPage() {
  const { data: agents } = usePoll<Agent[]>("/agents", 6000);
  const [open, setOpen] = React.useState<string | null>(null);
  const groups: [string, Agent[]][] = [
    ["Core", (agents ?? []).filter((a) => a.kind === "core" && a.role !== "council_judge")],
    ["Specialists", (agents ?? []).filter((a) => a.kind === "seed")],
    ["Created by evolution", (agents ?? []).filter((a) => a.kind === "spawned")],
    ["Performance council", (agents ?? []).filter((a) => a.role === "council_judge")],
  ];
  return (
    <div className="space-y-5">
      <div>
        <Label>Agent registry</Label>
        <h1 className="text-2xl font-semibold tracking-tight">Agents</h1>
        <p className="text-sm text-foreground-muted mt-1 max-w-2xl">
          Every agent is data: instructions, tools, capability tags and a model tier. That is how the system can refine an agent,
          specialise one, or create a new one when a capability is missing.
        </p>
      </div>
      {groups.map(([title, list]) =>
        list.length ? (
          <Panel key={title} title={`${title} (${list.length})`}>
            <div className="divide-y divide-border-subtle">
              {list.map((a) => (
                <div key={a.id} className="py-2">
                  <button onClick={() => setOpen(open === a.id ? null : a.id)} className="w-full flex flex-wrap items-center gap-3 text-left">
                    <span className={cn("text-sm w-56", a.kind === "spawned" && "text-amber-highlight")}>{a.name}</span>
                    <span className="text-xs text-foreground-muted w-32">{TIERS[a.current_version?.model ?? ""] ?? "-"}</span>
                    <span className="text-[11px] font-mono text-foreground-faint flex-1 truncate">
                      {a.current_version?.capability_tags.join(", ")}
                    </span>
                    {a.kind === "spawned" && <span className="text-[10px] font-mono text-amber-highlight">{a.origin}</span>}
                    <span className="font-mono text-xs text-foreground-secondary w-16 text-right">
                      {a.rolling_reward !== null ? `R ${pct(a.rolling_reward)}` : ""}
                    </span>
                    <Status value={a.status} />
                  </button>
                  {open === a.id && <AgentDetail agent={a} />}
                </div>
              ))}
            </div>
          </Panel>
        ) : null,
      )}
    </div>
  );
}

function AgentDetail({ agent }: { agent: Agent }) {
  const { data: versions } = usePoll<Version[]>(`/agents/${agent.id}/versions`, 10000);
  const latest = versions?.[versions.length - 1];
  const { data: detail } = usePoll<Version>(latest ? `/agents/${agent.id}/versions/${latest.version}` : null, 30000);
  return (
    <div className="mt-3 grid md:grid-cols-3 gap-3">
      <div>
        <Label>Versions</Label>
        <div className="space-y-1">
          {(versions ?? []).map((v) => (
            <div key={v.version} className="text-xs">
              <span className="font-mono text-cyan-highlight">v{v.version}</span>{" "}
              <span className="text-foreground-muted">{v.reason}</span>
            </div>
          ))}
        </div>
        <div className="mt-2">
          <Label>Tools</Label>
          <div className="text-xs text-foreground-muted">{agent.current_version?.tools.join(", ")}</div>
        </div>
      </div>
      <div className="md:col-span-2">
        <Label>Instructions (current version)</Label>
        <Json value={detail?.system_prompt ?? "loading"} max={6000} />
      </div>
    </div>
  );
}
