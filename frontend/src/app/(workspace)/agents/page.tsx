"use client";

import * as React from "react";
import { CaretDown } from "@phosphor-icons/react";
import { usePoll } from "@/lib/hooks";
import type { Agent } from "@/lib/types";
import { TIERS } from "@/lib/types";
import { cn } from "@/lib/utils";
import { ago, num } from "@/lib/workspace/model";
import { Card, Group, Pre, Segmented, Skeleton, StatusBadge } from "@/components/workspace/ui";

interface Version {
  version: number;
  model: string;
  reason: string | null;
  created_at: string;
  system_prompt?: string;
}

type Filter = "all" | "evolved" | "council";

export default function AgentsV2() {
  const { data: agents } = usePoll<Agent[]>("/agents", 20000);
  const [open, setOpen] = React.useState<string | null>(null);
  const [filter, setFilter] = React.useState<Filter>("all");
  const all = agents ?? [];
  const spawned = all.filter((a) => a.kind === "spawned");

  const groups: { title: string; detail: string; list: Agent[] }[] = [
    { title: "Core", detail: "Run every time: intake, planning, execution and reporting.", list: all.filter((a) => a.kind === "core" && a.role !== "council_judge") },
    { title: "Specialists", detail: "Switched on when the research brief needs their skills.", list: all.filter((a) => a.kind === "seed") },
    { title: "Created by evolution", detail: "Written during runs to fill a missing skill or replace a weak agent.", list: spawned },
    { title: "Council", detail: "Three judges on different models. They score every agent task.", list: all.filter((a) => a.role === "council_judge") },
  ].filter((g) => {
    if (filter === "evolved") return g.title === "Created by evolution";
    if (filter === "council") return g.title === "Council";
    return true;
  });

  return (
    <div className="space-y-10">
      <header className="space-y-4">
        <div>
          <h1 className="text-[36px] sm:text-[42px] font-medium leading-[1.04] tracking-[-0.055em] text-v2-text">
            The agent <em className="v2-serif italic text-v2-accent">team.</em>
          </h1>
          <p className="text-[15px] text-v2-text2 mt-1 max-w-[62ch]">
            Each agent is data: instructions, tools, skills and a model. That is what lets EvoLab refine one, specialise one, or write a
            new one when a skill is missing.
          </p>
        </div>
        <Segmented
          label="Show agents"
          value={filter}
          onChange={setFilter}
          options={[
            { value: "all", label: "All" },
            { value: "evolved", label: `Evolved${spawned.length ? ` (${spawned.length})` : ""}` },
            { value: "council", label: "Council" },
          ]}
        />
      </header>

      {!agents ? (
        <Card className="p-5 space-y-3">
          {[0, 1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-12" />
          ))}
        </Card>
      ) : (
        groups.map((g) => (
          <Group key={g.title} title={g.title} detail={g.detail}>
            <Card>
              {!g.list.length ? (
                <p className="text-[14px] text-v2-text3 px-5 py-6 text-center">
                  None yet. When a run hits a skill no agent has, the evolution engine proposes one for your approval.
                </p>
              ) : (
                <ul className="divide-y divide-v2-line/[0.06]">
                  {g.list.map((a) => (
                    <AgentRow key={a.id} agent={a} open={open === a.id} onToggle={() => setOpen(open === a.id ? null : a.id)} />
                  ))}
                </ul>
              )}
            </Card>
          </Group>
        ))
      )}
    </div>
  );
}

function AgentRow({ agent: a, open, onToggle }: { agent: Agent; open: boolean; onToggle: () => void }) {
  const panelId = React.useId();
  const tags = a.current_version?.capability_tags ?? [];
  return (
    <li>
      <button
        onClick={onToggle}
        aria-expanded={open}
        aria-controls={panelId}
        className="w-full grid grid-cols-[1fr_auto] sm:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)_auto_auto] items-center gap-x-5 gap-y-1 px-5 py-3.5 text-left hover:bg-v2-line/[0.03] transition-colors"
      >
        <span className="min-w-0">
          <span className={cn("block text-[15px] truncate", a.kind === "spawned" ? "text-v2-purple font-medium" : "text-v2-text")}>{a.name}</span>
          <span className="block text-[12px] text-v2-text3 truncate">
            {TIERS[a.current_version?.model ?? ""] ?? a.current_version?.model ?? "No model"}
            {a.current_version ? `, version ${a.current_version.version}` : ""}
          </span>
        </span>
        <span className="hidden sm:block text-[12px] text-v2-text3 truncate">{tags.slice(0, 4).join(", ")}</span>
        <span className="hidden sm:block text-[14px] tnum text-v2-text2 w-12 text-right" title="Rolling reward">
          {a.rolling_reward !== null ? num(a.rolling_reward) : ""}
        </span>
        <span className="flex items-center gap-2">
          {a.status !== "active" && <StatusBadge status={a.status} />}
          <CaretDown size={14} className={cn("text-v2-text3 transition-transform", open && "rotate-180")} aria-hidden />
        </span>
      </button>
      {open && (
        <div id={panelId} className="px-5 pb-5">
          <AgentDetail agent={a} />
        </div>
      )}
    </li>
  );
}

function AgentDetail({ agent }: { agent: Agent }) {
  const { data: versions } = usePoll<Version[]>(`/agents/${agent.id}/versions`, 30000);
  const latest = versions?.[versions.length - 1];
  const { data: detail } = usePoll<Version>(latest ? `/agents/${agent.id}/versions/${latest.version}` : null, 60000);
  return (
    <div className="grid md:grid-cols-[minmax(0,1fr)_minmax(0,2fr)] gap-6 pt-2">
      <div className="space-y-5">
        <div>
          <h4 className="text-[13px] font-semibold text-v2-text mb-2">History</h4>
          {!versions ? (
            <Skeleton className="h-16" />
          ) : (
            <ol className="relative space-y-3 before:absolute before:left-[5px] before:top-1.5 before:bottom-1.5 before:w-px before:bg-v2-line/[0.12]">
              {[...versions].reverse().map((v) => (
                <li key={v.version} className="relative pl-5">
                  <span className="absolute left-0 top-1.5 w-[11px] h-[11px] rounded-full border-2 border-v2-accent bg-v2-surface" aria-hidden />
                  <div className="text-[13px] font-medium text-v2-text">
                    Version {v.version} <span className="font-normal text-v2-text3">{ago(v.created_at)}</span>
                  </div>
                  <div className="text-[13px] text-v2-text2">{v.reason ?? "Initial version"}</div>
                </li>
              ))}
            </ol>
          )}
        </div>
        <div>
          <h4 className="text-[13px] font-semibold text-v2-text mb-1">Tools</h4>
          <p className="text-[13px] text-v2-text2">{agent.current_version?.tools.join(", ") || "None"}</p>
        </div>
        {(agent.current_version?.capability_tags.length ?? 0) > 0 && (
          <div>
            <h4 className="text-[13px] font-semibold text-v2-text mb-1">Skills</h4>
            <p className="text-[13px] text-v2-text2 v2-mono">{agent.current_version!.capability_tags.join(", ")}</p>
          </div>
        )}
      </div>
      <div>
        <h4 className="text-[13px] font-semibold text-v2-text mb-2">Instructions</h4>
        {detail?.system_prompt ? <Pre className="max-h-96">{detail.system_prompt}</Pre> : <Skeleton className="h-40" />}
      </div>
    </div>
  );
}
