"use client";

// About and Contact: glass cards opened from the landing page footer.

import * as React from "react";
import { ArrowUpRight, BookOpen, Bug, CodeXml, Github, Laptop, Scale, ShieldCheck, Sparkles, Users } from "lucide-react";
import { GlassModal } from "./GlassModal";
import { useOpenWorkspace } from "./WorkspaceAccess";

const REPO = "https://github.com/ELEVATE-1-0/ELEV03";

type Kind = "about" | "contact";
const InfoContext = React.createContext<(k: Kind) => void>(() => undefined);

export function InfoProvider({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = React.useState<Kind | null>(null);
  return (
    <InfoContext.Provider value={setOpen}>
      {children}
      {open === "about" && <AboutCard onClose={() => setOpen(null)} />}
      {open === "contact" && <ContactCard onClose={() => setOpen(null)} />}
    </InfoContext.Provider>
  );
}

export function OpenInfo({ kind, className, children }: { kind: Kind; className?: string; children: React.ReactNode }) {
  const open = React.useContext(InfoContext);
  return (
    <button type="button" className={className} onClick={() => open(kind)}>
      {children}
    </button>
  );
}

const FACTS = [
  { Icon: Users, title: "A team of agents", body: "A Meta-Controller plans the work; specialists read the paper, audit the code, implement, evaluate and write the report." },
  { Icon: Scale, title: "A council of three judges", body: "Every agent task is scored by judges on three different models: GPT-5.6 Luna, DeepSeek V4 Pro and GPT-5 Mini." },
  { Icon: Sparkles, title: "Agents that evolve", body: "Weak agents are refined and missing skills get new agents. Each change needs your approval and passes a probation." },
  { Icon: Laptop, title: "Runs on your laptop", body: "Experiments run on your paired machine inside a locked folder. The cloud coordinates jobs; it never reaches in." },
  { Icon: ShieldCheck, title: "A complete record", body: "Verified lessons are kept in memory, every run is traced, and every deviation from the paper is written to the Ledger." },
];

function AboutCard({ onClose }: { onClose: () => void }) {
  const openWorkspace = useOpenWorkspace();
  return (
    <GlassModal labelledBy="about-title" onClose={onClose} wide>
      <h2 id="about-title">About EvoLab</h2>
      <p className="glass-sub glass-sub-wide">
        EvoLab turns a research claim into an experiment you approve, runs it on your own machine, and explains what happened, so the result is one you can defend.
      </p>
      <ul className="glass-facts">
        {FACTS.map(({ Icon, title, body }) => (
          <li key={title}>
            <span className="glass-fact-icon" aria-hidden="true">
              <Icon size={17} />
            </span>
            <div>
              <b>{title}</b>
              <p>{body}</p>
            </div>
          </li>
        ))}
      </ul>
      <div className="glass-actions">
        <a className="glass-secondary" href={REPO} target="_blank" rel="noreferrer">
          <Github size={16} /> Source on GitHub
        </a>
        <button
          type="button"
          className="glass-primary glass-primary-inline"
          onClick={() => {
            onClose();
            openWorkspace();
          }}
        >
          Open workspace <ArrowUpRight size={16} />
        </button>
      </div>
    </GlassModal>
  );
}

const CHANNELS = [
  { Icon: Bug, title: "Report a bug or ask for a feature", body: "Open an issue on GitHub with the details.", href: `${REPO}/issues/new` },
  { Icon: BookOpen, title: "Read the documentation", body: "Architecture, API contract, agents and decisions.", href: `${REPO}/tree/main/docs` },
  { Icon: CodeXml, title: "Browse the source", body: "Backend, laptop worker and this frontend.", href: REPO },
];

function ContactCard({ onClose }: { onClose: () => void }) {
  return (
    <GlassModal labelledBy="contact-title" onClose={onClose}>
      <h2 id="contact-title">Get in touch</h2>
      <p className="glass-sub">EvoLab is built in the open. The quickest way to reach the team is on GitHub.</p>
      <ul className="glass-links">
        {CHANNELS.map(({ Icon, title, body, href }) => (
          <li key={title}>
            <a href={href} target="_blank" rel="noreferrer">
              <span className="glass-fact-icon" aria-hidden="true">
                <Icon size={17} />
              </span>
              <span className="glass-link-copy">
                <b>{title}</b>
                <span>{body}</span>
              </span>
              <ArrowUpRight size={16} className="glass-link-arrow" aria-hidden="true" />
            </a>
          </li>
        ))}
      </ul>
    </GlassModal>
  );
}
