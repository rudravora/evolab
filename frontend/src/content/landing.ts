export interface EntryPath {
  id: string;
  title: string;
  summary: string;
  verdict: "reproduced" | "baseline_established" | "exploratory";
  verdictLabel: string;
  iconName: string;
  badge: string;
}

export interface HowItWorksStep {
  step: number;
  title: string;
  sentence: string;
  whatYouSee: string;
  chip: string;
  accent: "cyan" | "amber";
}

export interface ReportItem {
  target: string;
  paperClaim: string;
  yourRun: string;
  delta: string;
  verdict: "Reproduced" | "Partial" | "Baseline established";
}

export interface DifferenceEntry {
  title: string;
  whatWeFound: string;
  whatChanged: string;
}

export interface EvolutionPoint {
  title: string;
  description: string;
}

export const HERO_CONTENT = {
  headline: "From paper to proof, on your own laptop.",
  subline:
    "EvoLab turns a paper, question, codebase or dataset into an approved plan, runs it locally, and returns a report that explains its results.",
  primaryCta: "Start a run",
  secondaryCta: "Watch the demo",
  chips: [
    { id: "paper", label: "Paper", format: "PDF / arXiv", color: "cyan" },
    { id: "question", label: "Question", format: "Natural Language", color: "amber" },
    { id: "codebase", label: "Codebase", format: "GitHub / PyPI", color: "cyan" },
    { id: "dataset", label: "Dataset", format: "CSV / Parquet", color: "amber" },
  ],
  briefNode: {
    title: "Research Brief",
    subtext: "Ready to plan",
  },
};

export const ENTRY_PATHS: EntryPath[] = [
  {
    id: "paper",
    title: "Research Paper",
    summary:
      "Extracts mathematical formulas and model architectures, running direct verification sweeps against original publication tables.",
    verdict: "reproduced",
    verdictLabel: "Verdict: reproduced",
    iconName: "FileText",
    badge: "Paper Mode",
  },
  {
    id: "codebase",
    title: "Existing Codebase",
    summary:
      "Audits library architectures, resolves version discrepancies, and executes reproducible test suites.",
    verdict: "baseline_established",
    verdictLabel: "Verdict: baseline_established",
    iconName: "Code2",
    badge: "Codebase Mode",
  },
  {
    id: "dataset",
    title: "Tabular or Raw Dataset",
    summary:
      "Screens for data leakage, profiles target distributions, and standardizes validation splits across experiments.",
    verdict: "baseline_established",
    verdictLabel: "Verdict: baseline_established",
    iconName: "Database",
    badge: "Dataset Mode",
  },
  {
    id: "question",
    title: "Research Question",
    summary:
      "Translates open hypotheses into concrete tests, designing balanced experiments to investigate novel directions.",
    verdict: "exploratory",
    verdictLabel: "Verdict: exploratory",
    iconName: "HelpCircle",
    badge: "Exploratory Mode",
  },
];

export const HOW_IT_WORKS_STEPS: HowItWorksStep[] = [
  {
    step: 1,
    title: "Bring anything",
    sentence:
      "Add a paper, a question, a codebase or a dataset, alone or in any mix. Each one gets its own entry point.",
    whatYouSee: "Your inputs lined up, ready to go.",
    chip: "Paper · Question · Codebase · Dataset",
    accent: "cyan",
  },
  {
    step: 2,
    title: "We understand it",
    sentence:
      "Your inputs are read and connected, so EvoLab knows what you want to prove and what to compare against.",
    whatYouSee: "A one-page research brief.",
    chip: "Brief ready",
    accent: "amber",
  },
  {
    step: 3,
    title: "You approve the plan",
    sentence:
      "A clear step-by-step plan is drafted with an estimate of time and cost. Nothing expensive starts until you say yes.",
    whatYouSee: "A plan card you can approve, edit or reject, from desktop or phone.",
    chip: "Approve · Edit · Reject",
    accent: "cyan",
  },
  {
    step: 4,
    title: "It runs on your machine",
    sentence:
      "Work is carried out on your own laptop, so your data and code stay with you.",
    whatYouSee: "Live progress and logs as it runs.",
    chip: "Running locally",
    accent: "amber",
  },
  {
    step: 5,
    title: "It adapts",
    sentence:
      "When something unexpected shows up, like a failure, a new finding or a budget limit, the plan updates. You can pause, redirect or chat with it at any time.",
    whatYouSee: "A plan timeline showing every change and why it happened.",
    chip: "Plan updated",
    accent: "cyan",
  },
  {
    step: 6,
    title: "You get the story",
    sentence:
      "A report with results for every experiment, a clear verdict against what the paper claimed, and a plain explanation of why results differ.",
    whatYouSee: "A shareable report with verdicts and explanations.",
    chip: "Report ready",
    accent: "amber",
  },
];

export const SAMPLE_REPORT_ROWS: ReportItem[] = [
  {
    target: "Smooth function test",
    paperClaim: "1.42e-4 error",
    yourRun: "1.38e-4 error",
    delta: "-2.8%",
    verdict: "Reproduced",
  },
  {
    target: "Parameter efficiency",
    paperClaim: "3.2x fewer parameters",
    yourRun: "3.1x fewer parameters",
    delta: "-3.1%",
    verdict: "Baseline established",
  },
  {
    target: "Tabular dataset accuracy",
    paperClaim: "88.4%",
    yourRun: "82.1%",
    delta: "-6.3%",
    verdict: "Partial",
  },
];

export const DIFFERENCE_ENTRIES: DifferenceEntry[] = [
  {
    title: "Matched compute budgets",
    whatWeFound: "The original comparison gave the baseline a smaller compute budget.",
    whatChanged: "We re-ran both approaches with matched resources, bringing the gap within margin of error.",
  },
  {
    title: "Real-world data behavior",
    whatWeFound: "Real-world data behaves differently from the synthetic data in the paper.",
    whatChanged: "We normalized feature distributions, revealing where practical performance diverged.",
  },
];

export const EVOLUTION_POINTS: EvolutionPoint[] = [
  {
    title: "Learns from past runs",
    description: "Insights and verified solutions are preserved so future experiments start ahead.",
  },
  {
    title: "Expands capabilities",
    description: "When an investigation hits a novel challenge, EvoLab brings in the right tool for the task.",
  },
  {
    title: "You stay in control",
    description: "Every new plan adjustment requires your explicit approval before taking effect.",
  },
];
