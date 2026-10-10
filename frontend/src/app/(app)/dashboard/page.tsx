"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Copy, FlaskConical, Laptop, Play, Sparkles } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { fmtTime, usePoll } from "@/lib/hooks";
import type { Approval, Project, Worker } from "@/lib/types";
import { Btn, Empty, Field, Label, Panel, Status } from "@/components/app/bits";

interface Pairing {
  pairing_code: string;
  expires_at: string;
  command: string;
}

export default function DashboardPage() {
  const router = useRouter();
  const { data: workers, reload: reloadWorkers } = usePoll<Worker[]>("/workers", 10000);
  const { data: projects } = usePoll<Project[]>("/projects", 10000);
  const { data: approvals } = usePoll<Approval[]>("/approvals?status=pending", 10000);
  const [pairing, setPairing] = React.useState<Pairing | null>(null);
  const [form, setForm] = React.useState({ paper: "", repo: "", dataset: "", question: "", note: "", budget: "30" });
  const [busy, setBusy] = React.useState(false);
  const [err, setErr] = React.useState<string | null>(null);

  const online = (workers ?? []).filter((w) => w.status === "online" && !w.revoked);

  const pair = async () => setPairing(await api<Pairing>("/workers/pairing", "POST"));

  const start = async (example: boolean) => {
    setBusy(true);
    setErr(null);
    try {
      const inputs = [
        form.paper && { kind: "paper", source: "url", ref: form.paper },
        form.repo && { kind: "repo", source: "url", ref: form.repo },
        form.dataset && { kind: "dataset", source: form.dataset.startsWith("http") ? "url" : "worker_path", ref: form.dataset },
        form.question && { kind: "question", source: "text", ref: form.question },
        form.note && { kind: "note", source: "text", ref: form.note },
      ].filter(Boolean);
      const minutes = Math.max(5, Number(form.budget) || 30);
      const created = await api<{ run_id: string }>("/projects", "POST", {
        example,
        goal: form.question || undefined,
        inputs,
        budget: { max_wall_min: minutes, max_tokens: 15000 * minutes },
      });
      router.push(`/runs/${created.run_id}`);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : String(e));
      setBusy(false);
    }
  };

  const ps1 = pairing
    ? `$env:BACKEND_URL = "${new URL(pairing.command.split(" ")[0].split("=")[1]).origin}"; $env:PAIRING_CODE = "${pairing.pairing_code}"; $env:WORKSPACE_ROOT = "$PWD\\workspace"; py worker\\worker.py`
    : "";

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <Label>Research workspace</Label>
          <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
        </div>
        {(approvals ?? []).length > 0 && (
          <Link href={`/runs/${approvals![0].run_id}`} className="text-xs text-amber-highlight font-mono">
            {approvals!.length} approval{approvals!.length > 1 ? "s" : ""} waiting
          </Link>
        )}
      </div>

      <div className="grid lg:grid-cols-3 gap-5">
        <Panel title="Start a run" className="lg:col-span-2" glow="cyan">
          <p className="text-xs text-foreground-muted mb-3">
            Give any mix of a paper, a codebase, a dataset or a question. EvoLab builds a Research Brief, drafts a plan for your
            approval, then runs it on your laptop.
          </p>
          <div className="grid sm:grid-cols-2 gap-3">
            <div>
              <Label>Paper (arXiv or PDF URL)</Label>
              <Field placeholder="https://arxiv.org/abs/2404.19756" value={form.paper} onChange={(e) => setForm({ ...form, paper: e.target.value })} />
            </div>
            <div>
              <Label>Codebase (GitHub URL)</Label>
              <Field placeholder="https://github.com/KindXiaoming/pykan" value={form.repo} onChange={(e) => setForm({ ...form, repo: e.target.value })} />
            </div>
            <div>
              <Label>Dataset (URL or path on the laptop)</Label>
              <Field placeholder="https://example.org/data.csv" value={form.dataset} onChange={(e) => setForm({ ...form, dataset: e.target.value })} />
            </div>
            <div>
              <Label>Budget (minutes)</Label>
              <Field type="number" min={5} value={form.budget} onChange={(e) => setForm({ ...form, budget: e.target.value })} />
            </div>
            <div className="sm:col-span-2">
              <Label>Question</Label>
              <Field
                placeholder="Do KANs beat parameter-matched MLPs on real tabular data?"
                value={form.question}
                onChange={(e) => setForm({ ...form, question: e.target.value })}
              />
            </div>
          </div>
          {err && <div className="text-xs text-red-300 mt-3">{err}</div>}
          <div className="flex flex-wrap gap-2 mt-4">
            <Btn variant="cyan" disabled={busy || !(form.paper || form.repo || form.dataset || form.question)} onClick={() => start(false)}>
              <Play className="w-3.5 h-3.5" /> Start run
            </Btn>
            <Btn disabled={busy} onClick={() => start(true)}>
              <Sparkles className="w-3.5 h-3.5" /> Try the KAN example
            </Btn>
          </div>
        </Panel>

        <Panel
          title="Laptop worker"
          action={<Status value={online.length ? "online" : "offline"} />}
        >
          {online.length > 0 ? (
            <div className="space-y-2">
              {online.map((w) => (
                <div key={w.id} className="flex items-center gap-2 text-sm">
                  <Laptop className="w-4 h-4 text-cyan-highlight" />
                  <span>{w.name}</span>
                  <span className="text-xs text-foreground-faint font-mono">
                    {w.platform} · {w.capabilities?.cpu_cores ?? "?"} cores
                  </span>
                </div>
              ))}
              <p className="text-xs text-foreground-muted">Jobs run inside a locked folder on this machine. It only reaches out; nothing connects in.</p>
            </div>
          ) : (
            <div className="space-y-3">
              <p className="text-xs text-foreground-muted">No worker is online. Planning works without one; experiments wait for it.</p>
              <Btn variant="cyan" onClick={pair}>Pair a laptop</Btn>
              {pairing && (
                <div className="space-y-2">
                  <div className="text-xs">
                    Code <span className="font-mono text-cyan-highlight text-sm">{pairing.pairing_code}</span>{" "}
                    <span className="text-foreground-faint">(valid 10 min)</span>
                  </div>
                  <Label>Run in PowerShell, from the repo root</Label>
                  <div className="relative">
                    <pre className="text-[10px] font-mono bg-canvas-subtle border border-border-subtle rounded-btn p-2 pr-8 whitespace-pre-wrap break-all">{ps1}</pre>
                    <button
                      onClick={() => navigator.clipboard.writeText(ps1)}
                      className="absolute top-1.5 right-1.5 text-foreground-faint hover:text-foreground"
                      aria-label="Copy command"
                    >
                      <Copy className="w-3.5 h-3.5" />
                    </button>
                  </div>
                  <Btn variant="ghost" onClick={reloadWorkers}>I have started it</Btn>
                </div>
              )}
            </div>
          )}
        </Panel>
      </div>

      <Panel title="Runs">
        {!projects?.length ? (
          <Empty>No runs yet. Start one above, or try the KAN example.</Empty>
        ) : (
          <div className="divide-y divide-border-subtle">
            {projects.map((p) => (
              <Link
                key={p.id}
                href={p.latest_run ? `/runs/${p.latest_run.id}` : "#"}
                className="flex items-center gap-3 py-2.5 hover:bg-white/[0.02] -mx-2 px-2 rounded-btn"
              >
                <FlaskConical className="w-4 h-4 text-foreground-faint shrink-0" />
                <div className="min-w-0 flex-1">
                  <div className="text-sm truncate">{p.goal ?? p.name}</div>
                  <div className="text-[11px] text-foreground-faint font-mono">
                    {p.inputs.map((i) => i.kind).join(" + ")} · {fmtTime(p.created_at)}
                  </div>
                </div>
                {p.latest_run && (
                  <>
                    {p.latest_run.counts.pending_approvals > 0 && (
                      <span className="text-[10px] font-mono text-amber-highlight">{p.latest_run.counts.pending_approvals} to approve</span>
                    )}
                    <span className="hidden sm:inline text-[11px] font-mono text-foreground-faint">
                      {p.latest_run.usage.wall_min} min · {p.latest_run.usage.jobs} jobs
                    </span>
                    <Status value={p.latest_run.status} />
                  </>
                )}
              </Link>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}
