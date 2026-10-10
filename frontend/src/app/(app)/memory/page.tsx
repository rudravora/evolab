"use client";

import * as React from "react";
import { usePoll } from "@/lib/hooks";
import { Empty, Field, Json, Label, Panel } from "@/components/app/bits";

interface Entry {
  id: string;
  kind: string;
  source: "seeded" | "learned";
  content: Record<string, unknown>;
  success_count: number;
  fail_count: number;
  created_at: string;
  mirrored: boolean;
}

export default function MemoryPage() {
  const [q, setQ] = React.useState("");
  const [query, setQuery] = React.useState("");
  const { data } = usePoll<{ retrieved_by: string; entries: Entry[]; counts?: { seeded: number; learned: number } }>(
    query ? `/memory?q=${encodeURIComponent(query)}` : "/memory",
    6000,
  );
  return (
    <div className="space-y-5">
      <div>
        <Label>What the team has learned</Label>
        <h1 className="text-2xl font-semibold tracking-tight">Memory</h1>
        <p className="text-sm text-foreground-muted mt-1 max-w-2xl">
          Only verified lessons are saved (a fix counts only after the re-run passed). Each one is labelled seeded (written by us)
          or learned (found by the agents), and reused in later runs.
        </p>
      </div>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          setQuery(q);
        }}
        className="max-w-md"
      >
        <Field placeholder="Search memory, e.g. pykan AttributeError" value={q} onChange={(e) => setQ(e.target.value)} />
      </form>
      <Panel
        title={query ? `Results (retrieved by ${data?.retrieved_by ?? "..."})` : "All entries"}
        action={
          data?.counts && (
            <span className="text-xs font-mono text-foreground-faint">
              {data.counts.learned} learned · {data.counts.seeded} seeded
            </span>
          )
        }
      >
        {!data?.entries.length ? (
          <Empty>No lessons yet. They appear when the Debugger fixes a failure and the re-run passes.</Empty>
        ) : (
          <div className="space-y-3">
            {data.entries.map((e) => (
              <div key={e.id} className="rounded-btn border border-border-subtle bg-canvas-elevated p-3">
                <div className="flex items-center gap-2 mb-1.5">
                  <span
                    className={
                      e.source === "learned"
                        ? "text-[10px] font-mono uppercase px-2 py-0.5 rounded-full border bg-emerald-500/10 text-emerald-300 border-emerald-500/25"
                        : "text-[10px] font-mono uppercase px-2 py-0.5 rounded-full border bg-amber/10 text-amber-highlight border-amber/30"
                    }
                  >
                    {e.source}
                  </span>
                  <span className="text-xs font-mono text-cyan-highlight">{e.kind}</span>
                  <span className="text-[10px] font-mono text-foreground-faint">
                    {e.source} · used successfully {e.success_count}x{e.mirrored ? " · in Supermemory" : ""}
                  </span>
                </div>
                <Json value={e.content} max={1500} />
              </div>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}
