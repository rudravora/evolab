// Shapes returned by the backend (docs/API.md v0.6, shared/openapi.yaml). Only the fields the UI uses.

export type RunStatus = "planning" | "awaiting_approval" | "running" | "paused" | "done" | "failed" | "cancelled";

export interface Health {
  status: string;
  version: string;
  time: string;
  mode: "live" | "simulated";
}

export interface Run {
  id: string;
  project_id: string;
  goal: string | null;
  status: RunStatus;
  budget: { max_wall_min?: number; max_tokens?: number };
  usage: { wall_min: number; tokens: number; jobs: number };
  counts: { agents_active: number; branches: number; pending_approvals: number };
  started_at: string;
  ended_at: string | null;
}

export interface Project {
  id: string;
  name: string;
  goal: string | null;
  created_at: string;
  inputs: { id: string; kind: string; source: string; ref: string }[];
  latest_run: Run | null;
}

export interface Worker {
  id: string;
  name: string;
  status: "online" | "offline";
  platform: string | null;
  last_heartbeat: string | null;
  cpu_pct: number | null;
  ram_pct: number | null;
  capabilities: { cpu_cores?: number; ram_gb?: number } | null;
  revoked: boolean;
}

export interface Fact {
  fact: string;
  evidence: string;
}

export interface Brief {
  entry_types: string[];
  goal: string | null;
  domain: string | null;
  facts: Fact[];
  reference_targets: { type: string; source: string; rank: number }[];
  activation: { agent_id: string; active: boolean; reason: string }[];
  ready: boolean;
}

export interface Reward {
  reward: number | null;
  outcome: number | null;
  outcome_det: number | null;
  council_q: number | null;
  council_judges: number | null;
  council_disagreement: number | null;
  council_split: boolean | null;
  cost: number | null;
  feedback: "up" | "down" | null;
  tokens_in: number;
  tokens_out: number;
  wall_s: number;
}

export interface Task {
  id: string;
  run_id: string;
  task_type: string;
  graph_key: string | null;
  agent_id: string | null;
  agent_name: string | null;
  status: string;
  required_tags: string[];
  depends_on: string[];
  steps: number;
  error: string | null;
  created_at: string;
  ended_at: string | null;
  reward: Reward;
  input?: Record<string, unknown>;
  output?: Record<string, unknown> | null;
  signals?: { signal: string; evidence: string }[];
}

export interface Message {
  seq: number;
  role: string;
  content: string | null;
  tool_name: string | null;
  tool_args: unknown;
  tool_result: unknown;
  ts: string;
}

export interface Council {
  status: string;
  judges: {
    judge_agent_id: string;
    tier: string;
    scores: Record<string, number>;
    overall: number;
    rationale: string;
    failure_pattern: string | null;
    confidence: number;
  }[];
  q: number | null;
  disagreement: number | null;
  split: boolean | null;
}

export interface Approval {
  id: string;
  run_id: string | null;
  type: string;
  status: string;
  payload: Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
  requested_by: string | null;
  comment: string | null;
  expires_at: string | null;
  created_at: string;
}

export interface TreeNode {
  id: string;
  hypothesis: string;
  kind: string | null;
  status: string;
  decision: string | null;
  decision_reason: string | null;
  metrics: Record<string, number>;
  seeds: number[];
  delta_vs_baseline?: Record<string, { delta: number; beyond_seed_variance: boolean }>;
  children: TreeNode[];
}

export interface AgentNode {
  id: string;
  name: string;
  role: string;
  kind: string;
  status: string;
  origin: string;
  active_in_run: boolean;
  activation_reason: string | null;
  rolling_reward: number | null;
}

export interface Agent {
  id: string;
  name: string;
  role: string;
  kind: string;
  status: string;
  origin: string;
  evolvable: boolean;
  parent_ids: string[];
  current_version: { version: number; model: string; tools: string[]; capability_tags: string[] } | null;
  rolling_reward: number | null;
}

export interface StreamEvent {
  id: number;
  type: string;
  data: Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
}

export const TIERS: Record<string, string> = { strong: "GPT-5.6 Luna", code: "DeepSeek V4 Pro", fast: "GPT-5 Mini" };
