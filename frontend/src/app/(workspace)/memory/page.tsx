"use client";

import * as React from "react";
import { Brain, MagnifyingGlass } from "@phosphor-icons/react";
import { usePoll } from "@/lib/hooks";
import { ago, sentence } from "@/lib/workspace/model";
import { Card, Empty, Pre, Segmented, Skeleton, StatusBadge, json } from "@/components/workspace/ui";

interface Entry {
  id: string;
  kind: string;
  signature?: string | null;
  source: "seeded" | "learned";
  content: Record<string, unknown>;
  success_count: number;
  fail_count: number;
  created_at: string;
  last_used_at?: string | null;
  mirrored: boolean;
}

type Source = "all" | "learned" | "seeded";

/** The most readable line in a lesson: a known field if present, otherwise the first short string. */
function headline(e: Entry) {
  const c = e.content;
  for (const k of ["summary", "lesson", "title", "fix", "error", "description"]) {
    if (typeof c[k] === "string" && c[k]) return String(c[k]);
  }
  const first = Object.values(c).find((v) => typeof v === "string" && v.length < 200);
  return typeof first === "string" ? first : sentence(e.kind);
}

export default function MemoryV2() {
  const [q, setQ] = React.useState("");
  const [query, setQuery] = React.useState("");
  const [source, setSource] = React.useState<Source>("all");
  const params = new URLSearchParams();
  if (query) params.set("q", query);
  if (source !== "all") params.set("source", source);
  const qs = params.toString();
  const { data } = usePoll<{ retrieved_by?: string; entries: Entry[]; counts?: { seeded: number; learned: number } }>(
    `/memory${qs ? `?${qs}` : ""}`,
    20000,
  );

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-[36px] sm:text-[42px] font-medium leading-[1.04] tracking-[-0.055em] text-v2-text">
          Lessons that <em className="v2-serif italic text-v2-accent">earned their place.</em>
        </h1>
        <p className="text-[15px] text-v2-text2 mt-1 max-w-[62ch]">
          Lessons the team keeps between runs. A fix is saved only after the re-run passes. Each lesson says whether we seeded it or the
          agents learned it.
        </p>
      </header>

      <div className="flex flex-col sm:flex-row sm:items-center gap-3">
        <form
          role="search"
          onSubmit={(e) => {
            e.preventDefault();
            setQuery(q.trim());
          }}
          className="relative flex-1 max-w-md"
        >
          <label htmlFor="mem-q" className="sr-only">
            Search memory
          </label>
          <MagnifyingGlass size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-v2-text3 pointer-events-none" aria-hidden />
          <input
            id="mem-q"
            type="search"
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              if (!e.target.value) setQuery("");
            }}
            placeholder="Search, for example pykan AttributeError"
            className="w-full h-10 pl-10 pr-3 rounded-[7px] bg-v2-line/[0.06] text-[15px] text-v2-text placeholder:text-v2-text3 border border-transparent focus:outline-none focus:border-v2-accent focus:bg-v2-surface"
          />
        </form>
        <Segmented
          label="Filter by source"
          value={source}
          onChange={setSource}
          options={[
            { value: "all", label: "All" },
            { value: "learned", label: data?.counts ? `Learned (${data.counts.learned})` : "Learned" },
            { value: "seeded", label: data?.counts ? `Seeded (${data.counts.seeded})` : "Seeded" },
          ]}
        />
      </div>

      {query && data?.retrieved_by && (
        <p className="text-[13px] text-v2-text3 -mt-4">
          Found by {data.retrieved_by === "supermemory" ? "Supermemory semantic search" : `${data.retrieved_by} match`}.
        </p>
      )}

      {!data ? (
        <div className="space-y-3">
          <Skeleton className="h-28" />
          <Skeleton className="h-28" />
        </div>
      ) : !data.entries.length ? (
        <Card>
          <Empty icon={<Brain size={32} />} title={query ? "Nothing matches" : "No lessons yet"}>
            {query ? "Try different words, or clear the search." : "They appear when the Debugger fixes a failure and the re-run passes."}
          </Empty>
        </Card>
      ) : (
        <ul className="grid md:grid-cols-2 gap-4">
          {data.entries.map((e) => (
            <li key={e.id} className="v2-card p-5 flex flex-col min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <StatusBadge status={e.source === "learned" ? "done" : "proposed"} label={e.source === "learned" ? "Learned" : "Seeded"} />
                <span className="text-[12px] text-v2-text3">
                  {sentence(e.kind)}
                  {e.mirrored ? ", also in Supermemory" : ""}
                </span>
              </div>
              <p className="text-[15px] text-v2-text mt-2.5 leading-snug line-clamp-3">{headline(e)}</p>
              {e.signature && (
                <p className="v2-mono text-[12px] text-v2-text3 mt-1.5 truncate" title={e.signature}>
                  {e.signature}
                </p>
              )}
              <details className="mt-3">
                <summary className="cursor-pointer text-[13px] text-v2-accent font-medium">Full lesson</summary>
                <Pre className="mt-2 max-h-64">{json(e.content, 3000)}</Pre>
              </details>
              <p className="text-[12px] text-v2-text3 mt-auto pt-3 tnum">
                Helped {e.success_count} {e.success_count === 1 ? "time" : "times"}
                {e.fail_count ? `, missed ${e.fail_count}` : ""}, added {ago(e.created_at)}
              </p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
