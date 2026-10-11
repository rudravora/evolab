// v2 helpers: the response shapes the v1 types do not cover (docs/API.md), plus wording and formatting
// shared by the workspace pages. Pure functions only, so they are easy to test by hand.

import type { RunStatus, Task } from "@/lib/types";

export interface Job {
  id: string;
  run_id: string;
  task_id: string | null;
  worker_id: string | null;
  type: string;
  payload: Record<string, unknown>;
  risk: string;
  status: string;
  attempt: number;
  timeout_s: number;
  policy_reason: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  exit_code: number | null;
  stdout_tail: string | null;
  stderr_tail: string | null;
  metrics: Record<string, number> | null;
}

export interface JobLog {
  seq: number;
  attempt: number;
  stream: string;
  chunk: string;
  ts: string;
}

export interface Artifact {
  id: string;
  kind: string;
  name: string;
  size: number;
  created_at: string;
}

export interface Report {
  artifact_id: string;
  markdown: string;
  created_at: string;
  why_differs: { ledger_entry_id: string; explanation: string }[];
}

export interface LedgerEntry {
  id: string;
  category: string;
  description: string;
}

export interface ChatMessage {
  id: string;
  role: string;
  content: string;
}

export type Tone = "accent" | "green" | "orange" | "red" | "purple" | "neutral";

/** Status words from every table (runs, tasks, jobs, branches, approvals, workers) mapped to one colour. */
export function toneOf(status: string): Tone {
  if (["done", "expanded", "approved", "online", "active", "succeeded", "completed"].includes(status)) return "green";
  if (["running", "claimed", "planning", "queued", "waiting_for_job"].includes(status)) return "accent";
  if (["pending", "awaiting_approval", "waiting_for_approval", "proposed", "paused", "probation"].includes(status)) return "orange";
  if (["failed", "rejected", "expired", "timed_out", "error", "denied"].includes(status)) return "red";
  return "neutral";
}

export function isLive(status: string) {
  return ["running", "claimed", "planning"].includes(status);
}

export function isFinal(status?: RunStatus | string | null) {
  return status === "done" || status === "failed" || status === "cancelled";
}

const STATUS_WORDS: Record<string, string> = {
  awaiting_approval: "Needs approval",
  waiting_for_approval: "Needs approval",
  waiting_for_job: "Waiting for laptop",
  timed_out: "Timed out",
  done: "Done",
};

export function statusLabel(status: string) {
  return STATUS_WORDS[status] ?? sentence(status);
}

export function sentence(s: string) {
  const t = s.replaceAll("_", " ").trim();
  return t ? t[0].toUpperCase() + t.slice(1) : t;
}

export const EXECUTOR_TASKS = new Set(["run_baseline", "run_branches"]);

export function taskWho(t: Task) {
  if (t.agent_name) return t.agent_name;
  if (EXECUTOR_TASKS.has(t.task_type)) return "Executor";
  return t.agent_id ? agentShort(t.agent_id) : "Unassigned";
}

export function agentShort(id?: string | null) {
  return id ? sentence(id.replace(/^agt_/, "")) : "";
}

export function num(x: number | null | undefined, digits = 2) {
  return x === null || x === undefined || Number.isNaN(x) ? "-" : x.toFixed(digits);
}

/** Experiment metric: whole numbers stay whole (param_count 520), others get 4 decimals (test_rmse 0.1057). */
export function metric(v: unknown) {
  if (typeof v !== "number") return String(v);
  return Number.isInteger(v) ? v.toLocaleString() : v.toFixed(4);
}

export function compact(n: number) {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 10_000) return `${Math.round(n / 1000)}k`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

export function bytes(n: number) {
  if (n >= 1 << 20) return `${(n / (1 << 20)).toFixed(1)} MB`;
  if (n >= 1 << 10) return `${(n / (1 << 10)).toFixed(1)} KB`;
  return `${n} B`;
}

export function minutes(m: number) {
  if (m < 1) return `${Math.round(m * 60)} s`;
  if (m < 60) return `${m.toFixed(m < 10 ? 1 : 0)} min`;
  return `${Math.floor(m / 60)} h ${Math.round(m % 60)} min`;
}

export function duration(from?: string | null, to?: string | null) {
  if (!from) return "";
  const s = Math.max(0, ((to ? Date.parse(to) : Date.now()) - Date.parse(from)) / 1000);
  if (s < 60) return `${Math.round(s)} s`;
  return minutes(s / 60);
}

/** "just now", "4 min ago", "3 h ago", then a date. */
export function ago(iso?: string | null, now = Date.now()) {
  if (!iso) return "";
  const s = (now - Date.parse(iso)) / 1000;
  if (s < 45) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return new Date(iso).toLocaleDateString([], { month: "short", day: "numeric" });
}

export function clock(iso?: string | null) {
  return iso ? new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "";
}

/** Fraction 0..1, clamped; null when there is no limit. */
export function ratio(used: number, limit?: number | null) {
  if (!limit) return null;
  return Math.max(0, Math.min(1, used / limit));
}

/** 24-hour "09:41", for event timelines. */
export function hhmm(iso?: string | null) {
  return iso ? new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false }) : "";
}
