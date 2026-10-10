"use client";

import * as React from "react";
import { api, ApiError } from "./api";
import type { StreamEvent } from "./types";

/** Fetch `path` now and every `ms` milliseconds. Pass null to pause. */
export function usePoll<T>(path: string | null, ms = 3000) {
  const [data, setData] = React.useState<T | undefined>(undefined);
  const [error, setError] = React.useState<ApiError | null>(null);
  const [nonce, setNonce] = React.useState(0);

  React.useEffect(() => {
    if (!path) return;
    let alive = true;
    const load = () =>
      api<T>(path)
        .then((d) => {
          if (alive) {
            setData(d);
            setError(null);
          }
        })
        .catch((e: ApiError) => alive && setError(e));
    load();
    const id = window.setInterval(load, ms);
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, [path, ms, nonce]);

  const reload = React.useCallback(() => setNonce((n) => n + 1), []);
  return { data, error, reload };
}

const EVENT_TYPES = [
  "run.status", "agent.task", "agent.message", "agent.evolution", "agent.score", "agent.activation", "agent.probation",
  "job.status", "job.log", "job.requeued", "branch.update", "experiment.metrics", "ledger.entry", "memory.hit",
  "memory.write", "approval.requested", "approval.decided", "worker.status", "chat.message", "report.ready",
  "budget.warning", "intake.brief", "plan.revised", "candidates.ready", "capability.gap", "council.score",
];

/** Live run events over SSE (GET /runs/{id}/stream). Keeps the latest `keep` events. */
export function useRunStream(runId: string | null, keep = 250) {
  const [events, setEvents] = React.useState<StreamEvent[]>([]);
  const [connected, setConnected] = React.useState(false);
  const [lastType, setLastType] = React.useState<{ type: string; at: number } | null>(null);

  const [ended, setEnded] = React.useState(false);

  React.useEffect(() => {
    if (!runId) return;
    // The backend closes the stream once the run has ended; EventSource would otherwise reconnect
    // forever. So: remember the last id (resume after a network drop), ignore duplicates, and stop
    // for good after a final run.status.
    let lastId = 0;
    let finished = false;
    let es: EventSource | null = null;
    let retry: number | undefined;
    const handler = (type: string) => (msg: MessageEvent) => {
      const id = Number(msg.lastEventId);
      if (id && id <= lastId) return;
      lastId = id || lastId;
      const ev: StreamEvent = { id, type, data: JSON.parse(msg.data || "{}") };
      setEvents((prev) => [...prev.slice(-(keep - 1)), ev]);
      setLastType({ type, at: Date.now() });
      if (type === "run.status" && ["done", "failed", "cancelled"].includes(ev.data.status)) finished = true;
    };
    const handlers = EVENT_TYPES.map((t) => [t, handler(t)] as const);
    const open = () => {
      es = new EventSource(`/api/v1/runs/${runId}/stream?after_id=${lastId}`, { withCredentials: true });
      es.onopen = () => setConnected(true);
      es.onerror = () => {
        es?.close();
        setConnected(false);
        if (finished) setEnded(true);
        else retry = window.setTimeout(open, 3000);
      };
      handlers.forEach(([t, h]) => es!.addEventListener(t, h as EventListener));
    };
    open();
    return () => {
      window.clearTimeout(retry);
      es?.close();
    };
  }, [runId, keep]);

  return { events, connected, ended, lastType };
}

export function fmtTime(iso?: string | null) {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function pct(x: number | null | undefined) {
  return x === null || x === undefined ? "-" : x.toFixed(2);
}
