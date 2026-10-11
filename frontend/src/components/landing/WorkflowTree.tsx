"use client";

// "How it works": a vertical timeline. One rail runs through intake, brief and approval, forks
// into the primary run and a what-if lane, then rejoins at the evidence. The rail draws in and
// steps reveal as they scroll into view; with reduced motion everything is shown at once.

import { motion, useReducedMotion } from "framer-motion";

type Step = { number: string; phase: string; title: string; body: string; tags: string[]; gate?: boolean };

const before: Step[] = [
  {
    number: "01",
    phase: "Before work",
    title: "Bring what you have",
    body: "Combine a paper, question, codebase and dataset—or begin with just one.",
    tags: ["Paper", "Question", "Code", "Dataset"],
  },
  {
    number: "02",
    phase: "Before work",
    title: "Build the research brief",
    body: "Connect claims and references to the facts detected in your inputs.",
    tags: ["Facts with sources", "Reference targets"],
  },
  {
    number: "03",
    phase: "Your decision",
    title: "Approve the plan",
    body: "Review the task graph, active agents, target and estimated budget before work begins.",
    tags: ["Approve", "Edit", "Send back"],
    gate: true,
  },
];

const lanes: Step[] = [
  {
    number: "04A",
    phase: "On your laptop",
    title: "Run the primary test",
    body: "Jobs run on your paired worker while progress, logs and changes stay in view.",
    tags: ["Locked folder", "Live logs"],
  },
  {
    number: "04B",
    phase: "In parallel",
    title: "Open a what-if branch",
    body: "Test an alternative or recover from new evidence—with a reason attached to the branch.",
    tags: ["Reason recorded"],
  },
];

const after: Step = {
  number: "05",
  phase: "After the run",
  title: "Rejoin at the evidence",
  body: "Compare each outcome with the reference, then keep the verdict, decisions and deviations in the report and Ledger.",
  tags: ["Verdict", "Report", "Ledger"],
};

function reveal(reduced: boolean, delay = 0) {
  return {
    initial: reduced ? false : ({ opacity: 0, y: 14 } as const),
    whileInView: { opacity: 1, y: 0 },
    viewport: { once: true, amount: 0.3 },
    transition: reduced ? { duration: 0 } : { duration: 0.45, delay, ease: "easeOut" as const },
  };
}

function Card({ step, lane }: { step: Step; lane?: boolean }) {
  return (
    <div className={`timeline-card${step.gate ? " is-gate" : ""}${lane ? " is-lane" : ""}`}>
      <span className="timeline-card-number mono">{step.number}</span>
      <h3>{step.title}</h3>
      <p>{step.body}</p>
      <ul className="timeline-tags" aria-label="Includes">
        {step.tags.map((t) => (
          <li key={t}>{t}</li>
        ))}
      </ul>
    </div>
  );
}

function Row({ step, reduced, delay }: { step: Step; reduced: boolean; delay: number }) {
  return (
    <motion.li className={`timeline-row${step.gate ? " is-gate" : ""}`} {...reveal(reduced, delay)}>
      <span className="timeline-phase mono">{step.phase}</span>
      <span className="timeline-marker" aria-hidden="true" />
      <Card step={step} />
    </motion.li>
  );
}

export default function WorkflowTree() {
  const reduced = useReducedMotion() ?? false;
  return (
    <ol className="workflow-timeline" aria-label="How an EvoLab run unfolds, step by step">
      <motion.span
        className="timeline-rail"
        aria-hidden="true"
        initial={reduced ? false : { scaleY: 0 }}
        whileInView={{ scaleY: 1 }}
        viewport={{ once: true, amount: 0.05 }}
        transition={reduced ? { duration: 0 } : { duration: 1.6, ease: "easeOut" }}
      />

      {before.map((s, i) => (
        <Row key={s.number} step={s} reduced={reduced} delay={i * 0.05} />
      ))}

      <motion.li className="timeline-row timeline-fork" {...reveal(reduced, 0.05)}>
        <span className="timeline-phase mono">Two paths</span>
        <span className="timeline-marker is-fork" aria-hidden="true" />
        <div className="timeline-lanes">
          <span className="timeline-fork-bar" aria-hidden="true" />
          <span className="timeline-merge-bar" aria-hidden="true" />
          {lanes.map((s) => (
            <div key={s.number} className="timeline-lane">
              <span className="timeline-lane-phase mono">{s.phase}</span>
              <Card step={s} lane />
            </div>
          ))}
        </div>
      </motion.li>

      <Row step={after} reduced={reduced} delay={0.05} />
    </ol>
  );
}
