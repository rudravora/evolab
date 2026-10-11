"use client";

// EvoLab landing page, ported from the final EvoLab UI prototype (Manus) as it was.
// Changes for the real app only: dark appearance only (no theme toggle), and every
// "Open workspace" control opens the sign-in card (WorkspaceAccess) or the dashboard.
// Styles: src/app/landing.css, scoped to .evo-landing.

import { motion, useReducedMotion } from "framer-motion";
import { ArrowRight, ArrowUpRight, Atom, FlaskConical, GitBranch, ShieldCheck, Sparkles } from "lucide-react";
import EvoMark from "./EvoMark";
import ResearchScrollStory from "./ResearchScrollStory";
import WorkflowTree from "./WorkflowTree";
import { OpenWorkspace, WorkspaceAccessProvider } from "./WorkspaceAccess";

const proofPoints = [
  {
    icon: ShieldCheck,
    eyebrow: "Human-directed",
    title: "You approve the plan.",
    body: "EvoLab lays out the work, active agents and estimated cost before an experiment begins. Approve, edit or send it back.",
  },
  {
    icon: Atom,
    eyebrow: "Runs where you work",
    title: "Your laptop does the work.",
    body: "Code and datasets run on your own paired worker. The cloud coordinates jobs; it doesn’t reach into your machine.",
  },
  {
    icon: GitBranch,
    eyebrow: "A complete record",
    title: "Nothing disappears into a chat.",
    body: "Every adjustment, re-plan and branch is recorded with evidence—so the result stays explainable after the run.",
  },
];

function LandingHeader() {
  return (
    <header className="marketing-header">
      <EvoMark />
      <nav className="marketing-nav" aria-label="Main navigation">
        <a href="#journey">The journey</a>
        <a href="#method">How it works</a>
        <a href="#principles">The difference</a>
      </nav>
      <OpenWorkspace className="button button-dark header-action">
        Open workspace <ArrowUpRight size={15} />
      </OpenWorkspace>
    </header>
  );
}

export function Landing({ openAccess = false, next }: { openAccess?: boolean; next?: string }) {
  const reduceMotion = useReducedMotion();
  return (
    <div className="evo-landing">
      <WorkspaceAccessProvider initialOpen={openAccess} next={next}>
        <div className="marketing-page">
          <LandingHeader />
          <main>
            <ResearchScrollStory />

            <section className="workflow-section" id="method">
              <div className="shell workflow-intro">
                <div className="section-kicker">
                  <span className="mono">THE METHOD</span>
                  <span className="kicker-line" />
                </div>
                <div className="workflow-heading-row">
                  <h2>
                    One approved plan.
                    <br />
                    <em>Two paths to evidence.</em>
                  </h2>
                  <p>
                    Start from a shared research brief. After approval, the primary experiment and a reasoned what-if can branch independently before
                    their evidence rejoins in the report and Ledger.
                  </p>
                </div>
                <WorkflowTree />
              </div>
            </section>

            <motion.section
              className="sample-story-section shell"
              initial={reduceMotion ? false : { opacity: 0, y: 18 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, amount: 0.18 }}
              transition={reduceMotion ? { duration: 0 } : { duration: 0.6, ease: "easeOut" }}
            >
              <div className="sample-story-copy">
                <div className="section-kicker">
                  <span className="mono">A SAMPLE RUN</span>
                  <span className="kicker-line" />
                </div>
                <h2>
                  Research rarely
                  <br />
                  goes <em>in a straight line.</em>
                </h2>
                <p>
                  Take one real research question: <strong>Do KANs beat parameter-matched MLPs on tabular data?</strong> EvoLab finds the paper and
                  official code, checks a new dataset, and adapts the plan when it spots a potential leakage issue.
                </p>
                <OpenWorkspace className="text-link story-link">
                  Follow the sample run <ArrowRight size={15} />
                </OpenWorkspace>
              </div>
              <div className="sample-route" aria-label="Illustrative route from research question to report">
                <div className="route-node route-node-start">
                  <span className="route-node-icon">
                    <Sparkles size={15} />
                  </span>
                  <span className="mono">THE QUESTION</span>
                  <b>Do KANs win?</b>
                </div>
                <div className="route-path">
                  <span className="route-path-dot" />
                </div>
                <div className="route-event">
                  <span className="route-event-marker">
                    <FlaskConical size={15} />
                  </span>
                  <div>
                    <span className="mono">NEW EVIDENCE · 09:51</span>
                    <b>Identifier flagged</b>
                    <small>Minor re-plan · reason recorded</small>
                  </div>
                </div>
                <div className="route-path route-path-branch">
                  <span className="route-path-dot" />
                </div>
                <div className="route-fork">
                  <div className="route-fork-line" />
                  <div className="route-fork-result">
                    <span className="result-mark result-mark-partial" />
                    Paper claim <strong>partial</strong>
                  </div>
                  <div className="route-fork-result">
                    <span className="result-mark" />
                    Transfer check <strong>in progress</strong>
                  </div>
                </div>
                <div className="route-foot mono">ILLUSTRATIVE UI DATA · EVIDENCE OVER ASSUMPTION</div>
              </div>
            </motion.section>

            <section className="principles-section" id="principles">
              <div className="shell">
                <div className="section-kicker">
                  <span className="mono">WHY EVOLAB</span>
                  <span className="kicker-line" />
                </div>
                <div className="principles-heading">
                  <h2>
                    Built for the part
                    <br />
                    after <em>“it works on my machine.”</em>
                  </h2>
                  <p>Research needs more than an answer. It needs a route to the answer that someone else can inspect.</p>
                </div>
                <div className="principles-list">
                  {proofPoints.map(({ icon: Icon, eyebrow, title, body }, index) => (
                    <motion.article
                      className="principle-row"
                      key={title}
                      initial={reduceMotion ? false : { opacity: 0, y: 12 }}
                      whileInView={{ opacity: 1, y: 0 }}
                      viewport={{ once: true, amount: 0.3 }}
                      transition={reduceMotion ? { duration: 0 } : { duration: 0.4, delay: index * 0.07 }}
                    >
                      <span className="principle-index mono">0{index + 1}</span>
                      <span className="principle-icon">
                        <Icon size={18} strokeWidth={1.6} />
                      </span>
                      <div className="principle-copy">
                        <span className="mono principle-eyebrow">{eyebrow}</span>
                        <h3>{title}</h3>
                      </div>
                      <p>{body}</p>
                    </motion.article>
                  ))}
                </div>
              </div>
            </section>

            <motion.section
              className="landing-cta shell"
              initial={reduceMotion ? false : { opacity: 0, y: 18 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, amount: 0.25 }}
              transition={reduceMotion ? { duration: 0 } : { duration: 0.55, ease: "easeOut" }}
            >
              <div className="cta-orbit" aria-hidden="true">
                <span />
                <span />
                <span />
              </div>
              <div className="cta-content">
                <span className="mono">A BETTER WAY TO TEST A CLAIM</span>
                <h2>
                  Make your next result
                  <br />
                  <em>easier to believe.</em>
                </h2>
                <p>Start with what you have. Keep your hands on the plan.</p>
                <OpenWorkspace className="button button-light">
                  See the EvoLab workspace <ArrowRight size={16} />
                </OpenWorkspace>
              </div>
              <span className="cta-caption mono">
                NO MAGIC BOX.
                <br />
                JUST GOOD SCIENCE.
              </span>
            </motion.section>
          </main>
          <footer className="site-footer">
            <div className="shell">
              <div className="site-footer-top">
                <div className="site-footer-brand">
                  <EvoMark />
                  <p>A considered workflow for computational research: from a claim to a result you can defend, run on your own machine.</p>
                  <OpenWorkspace className="button button-light">
                    Open workspace <ArrowUpRight size={15} />
                  </OpenWorkspace>
                </div>
                <nav className="site-footer-col" aria-label="Product">
                  <h3>Product</h3>
                  <ul>
                    <li>
                      <a href="#journey">The journey</a>
                    </li>
                    <li>
                      <a href="#method">How it works</a>
                    </li>
                    <li>
                      <a href="#principles">The difference</a>
                    </li>
                  </ul>
                </nav>
                <nav className="site-footer-col" aria-label="Workspace">
                  <h3>Workspace</h3>
                  <ul>
                    <li>
                      <OpenWorkspace className="">Sign in</OpenWorkspace>
                    </li>
                    <li>
                      <OpenWorkspace className="">Try the KAN example</OpenWorkspace>
                    </li>
                    <li>
                      <OpenWorkspace className="">Pair a laptop</OpenWorkspace>
                    </li>
                  </ul>
                </nav>
                <nav className="site-footer-col" aria-label="Project">
                  <h3>Project</h3>
                  <ul>
                    <li>
                      <a href="https://github.com/ELEVATE-1-0/ELEV03" target="_blank" rel="noreferrer">
                        Source on GitHub
                      </a>
                    </li>
                    <li>
                      <a href="https://github.com/ELEVATE-1-0/ELEV03/tree/main/docs" target="_blank" rel="noreferrer">
                        Documentation
                      </a>
                    </li>
                    <li>
                      <a href="https://github.com/ELEVATE-1-0/ELEV03/issues" target="_blank" rel="noreferrer">
                        Report an issue
                      </a>
                    </li>
                  </ul>
                </nav>
              </div>
              <div className="site-footer-bottom">
                <span>© 2026 EvoLab</span>
                <span className="mono">EVIDENCE OVER ASSUMPTION</span>
              </div>
            </div>
          </footer>
        </div>
      </WorkspaceAccessProvider>
    </div>
  );
}
