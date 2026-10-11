"use client";

// Ported from the EvoLab UI prototype; the only changes: Next.js imports, and "Open workspace"
// opens the sign-in card (WorkspaceAccess) instead of a demo route.

import {
  AnimatePresence,
  motion,
  useAnimationFrame,
  useInView,
  useMotionValue,
  useReducedMotion,
  useTransform,
} from "framer-motion";
import type { MotionValue } from "framer-motion";
import { ArrowRight, Pause, Play } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { OpenWorkspace } from "./WorkspaceAccess";

const filmPath = "/evolab-research-film.mp4";
const posterPath = "/evolab-research-film-poster.jpg";
const STORY_CYCLE_MS = 30_000;

const beats = [
  { kicker: "01 · THE CLAIM", title: "One question at the centre.", body: "Begin with a paper, a dataset, a codebase—or a question on its own." },
  { kicker: "02 · LINKED EVIDENCE", title: "Sources find each other.", body: "Claims, references and data connect into a brief you can inspect." },
  { kicker: "03 · RESEARCHER APPROVAL", title: "A test gets a human yes.", body: "See the task graph, chosen agents, target and budget before anything runs." },
  { kicker: "04 · BRANCHES WITH REASONS", title: "The evidence changes the path.", body: "A useful what-if branches; a risky one can be set aside—with the reason recorded." },
  { kicker: "05 · AUDITABLE RESULT", title: "Every path leaves a trace.", body: "Compare outcomes with the claim, then keep the decisions and deviations in the Ledger." },
];

type GraphProps = {
  activeBeat: number;
  reducedMotion: boolean;
  claimPath: MotionValue<number>;
  evidencePath: MotionValue<number>;
  planPath: MotionValue<number>;
  branchPath: MotionValue<number>;
  reportPath: MotionValue<number>;
  rotateX: MotionValue<number>;
  rotateY: MotionValue<number>;
  rotateZ: MotionValue<number>;
  scale: MotionValue<number>;
  depth: MotionValue<number>;
};

const edges = [
  { className: "edge-claim", d: "M300 250 C245 210 195 160 112 108" },
  { className: "edge-evidence", d: "M300 250 C370 215 420 160 488 112" },
  { className: "edge-plan", d: "M300 250 C309 177 325 110 350 48" },
  { className: "edge-branch", d: "M488 112 C505 160 509 204 498 245 M514 350 C510 310 505 281 498 245" },
  { className: "edge-report", d: "M300 250 C310 324 311 390 305 454 M112 390 C170 427 228 451 305 454" },
];

function GraphScene({
  activeBeat, reducedMotion, claimPath, evidencePath, planPath, branchPath, reportPath,
  rotateX, rotateY, rotateZ, scale, depth,
}: GraphProps) {
  const progress = [claimPath, evidencePath, planPath, branchPath, reportPath];
  return (
    <div className="research-graph-frame" aria-hidden="true">
      <div className="research-graph-stamp mono">EVIDENCE MAP · EV-0426</div>
      <motion.div
        className="research-graph"
        data-beat={activeBeat}
        style={reducedMotion ? { transformPerspective: 1200, transformStyle: "preserve-3d" } : { rotateX, rotateY, rotateZ, scale, z: depth, transformPerspective: 1200, transformStyle: "preserve-3d" }}
      >
        <div className="graph-orbit graph-orbit-a" />
        <div className="graph-orbit graph-orbit-b" />
        <div className="graph-orbit graph-orbit-c" />
        <svg className="graph-edges" viewBox="0 0 600 500" preserveAspectRatio="xMidYMid meet">
          <defs>
            <linearGradient id="evolab-edge" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stopColor="var(--teal)" />
              <stop offset="66%" stopColor="var(--teal-dark)" />
              <stop offset="100%" stopColor="var(--gold)" />
            </linearGradient>
          </defs>
          {edges.map((edge, index) => (
            <motion.path
              key={edge.className}
              className={`graph-edge ${edge.className}`}
              d={edge.d}
              pathLength={reducedMotion ? 1 : progress[index]}
              fill="none"
              stroke="url(#evolab-edge)"
              strokeWidth="1.35"
              strokeLinecap="round"
            />
          ))}
        </svg>
        <div className="graph-node graph-node-question" style={{ left: "50%", top: "50%", transform: "translate3d(-50%, -50%, 46px)" }}>
          <span className="graph-node-orb" /><span className="graph-node-label mono">THE CLAIM</span>
        </div>
        <div className="graph-node graph-node-paper" style={{ left: "18.7%", top: "21.6%", transform: "translate3d(-50%, -50%, 12px)" }}>
          <span className="graph-node-orb" /><span className="graph-node-label mono">PAPER</span>
        </div>
        <div className="graph-node graph-node-code" style={{ left: "81.3%", top: "21.6%", transform: "translate3d(-50%, -50%, -16px)" }}>
          <span className="graph-node-orb" /><span className="graph-node-label mono">CODE</span>
        </div>
        <div className="graph-node graph-node-dataset" style={{ left: "85.7%", top: "70.4%", transform: "translate3d(-50%, -50%, 28px)" }}>
          <span className="graph-node-orb" /><span className="graph-node-label mono">DATA</span>
        </div>
        <div className="graph-node graph-node-agent" style={{ left: "18.7%", top: "78.4%", transform: "translate3d(-50%, -50%, -8px)" }}>
          <span className="graph-node-orb" /><span className="graph-node-label mono">AGENTS</span>
        </div>
        <div className="graph-node graph-node-plan" style={{ left: "58.3%", top: "9.6%", transform: "translate3d(-50%, -50%, 54px)" }}>
          <span className="graph-node-orb" /><span className="graph-node-label mono">APPROVED PLAN</span>
        </div>
        <div className="graph-node graph-node-branch" style={{ left: "83%", top: "49%", transform: "translate3d(-50%, -50%, 38px)" }}>
          <span className="graph-node-orb" /><span className="graph-node-label mono">WHAT-IF</span>
        </div>
        <div className="graph-node graph-node-report" style={{ left: "50.8%", top: "91%", transform: "translate3d(-50%, -50%, 72px)" }}>
          <span className="graph-node-orb" /><span className="graph-node-label mono">REPORT</span>
        </div>
        <div className="graph-center-glow" />
      </motion.div>
      <div className="research-graph-caption"><span className="graph-caption-dot" /> A route you can follow, not an answer in a black box.</div>
    </div>
  );
}

function BeatButton({
  index, activeBeat, progress, onSelect,
}: { index: number; activeBeat: number; progress: MotionValue<number>; onSelect: () => void }) {
  const fill = useTransform(progress, [index / beats.length, (index + 1) / beats.length], [0, 1]);
  return (
    <button
      type="button"
      aria-label={`Show stage ${index + 1}: ${beats[index].title}`}
      aria-current={activeBeat === index ? "step" : undefined}
      onClick={onSelect}
    >
      <span className="research-story-nav-track"><motion.span style={{ scaleX: fill }} /></span>
      <span className="mono">0{index + 1}</span>
    </button>
  );
}

export default function ResearchScrollStory() {
  const sectionRef = useRef<HTMLElement>(null);
  const filmRef = useRef<HTMLVideoElement>(null);
  const runningRef = useRef(false);
  const reducedMotion = useReducedMotion() ?? false;
  const visible = useInView(sectionRef, { amount: 0.14 });
  const progress = useMotionValue(0);
  const [activeBeat, setActiveBeat] = useState(0);
  const [isPlaying, setIsPlaying] = useState(!reducedMotion);
  const [filmReady, setFilmReady] = useState(false);
  const [filmFailed, setFilmFailed] = useState(false);

  useEffect(() => {
    if (reducedMotion) setIsPlaying(false);
  }, [reducedMotion]);

  useEffect(() => {
    runningRef.current = isPlaying && visible && !reducedMotion && !filmFailed;
    const film = filmRef.current;
    if (!film || filmFailed) return;
    if (runningRef.current) {
      void film.play().catch(() => setIsPlaying(false));
    } else {
      film.pause();
    }
  }, [isPlaying, visible, reducedMotion, filmFailed]);

  useAnimationFrame((_time, delta) => {
    if (!runningRef.current) return;
    const nextProgress = (progress.get() + delta / STORY_CYCLE_MS) % 1;
    progress.set(nextProgress);
    const nextBeat = Math.min(beats.length - 1, Math.floor(nextProgress * beats.length));
    setActiveBeat((current) => current === nextBeat ? current : nextBeat);
  });

  const rotateX = useTransform(progress, [0, 0.5, 1], reducedMotion ? [0, 0, 0] : [7, -4, 7]);
  const rotateY = useTransform(progress, [0, 0.5, 1], reducedMotion ? [0, 0, 0] : [-6, 7, -6]);
  const rotateZ = useTransform(progress, [0, 0.5, 1], reducedMotion ? [0, 0, 0] : [-1.5, 1.5, -1.5]);
  const scale = useTransform(progress, [0, 0.38, 0.72, 1], reducedMotion ? [1, 1, 1, 1] : [0.96, 1.02, 0.98, 0.96]);
  const depth = useTransform(progress, [0, 0.5, 1], reducedMotion ? [0, 0, 0] : [-8, 24, -8]);
  const claimPath = useTransform(progress, [0, 0.06, 0.22, 1], [0, 0.1, 1, 1]);
  const evidencePath = useTransform(progress, [0, 0.2, 0.42, 1], [0, 0, 1, 1]);
  const planPath = useTransform(progress, [0, 0.38, 0.62, 1], [0, 0, 1, 1]);
  const branchPath = useTransform(progress, [0, 0.55, 0.82, 1], [0, 0, 1, 1]);
  const reportPath = useTransform(progress, [0, 0.78, 1], [0, 0, 1]);

  const handleFilmReady = () => setFilmReady(true);
  const handleFilmError = () => {
    setFilmReady(false);
    setFilmFailed(true);
  };
  const selectBeat = (index: number) => {
    const nextProgress = (index + 0.02) / beats.length;
    progress.set(nextProgress);
    setActiveBeat(index);
  };
  const togglePlayback = () => setIsPlaying((current) => !current);

  if (reducedMotion || filmFailed) {
    return (
      <section className="research-scroll-story is-static" id="journey" aria-labelledby="research-story-title" ref={sectionRef}>
        <div className="research-story-static-film">
          <img src={posterPath} alt="" aria-hidden="true" />
          <span className="mono">FILM STILL · REDUCED-MOTION VIEW</span>
        </div>
        <div className="research-story-static shell">
          <div className="research-story-static-heading">
            <div className="section-kicker"><span className="mono">A RESEARCH WORKFLOW THAT SHOWS ITS WORK</span><span className="kicker-line" /></div>
            <h1 id="research-story-title">From a claim to<br /><em>a result you can defend.</em></h1>
            <p>{reducedMotion ? "Motion is off because reduced motion is enabled. The complete five-stage story is listed below." : "The film could not load, so the complete five-stage story is shown as a still."}</p>
            <OpenWorkspace className="button button-light story-primary-action">Open the EvoLab workspace <ArrowRight size={16} /></OpenWorkspace>
          </div>
          <ol className="research-story-static-steps">
            {beats.map((beat, index) => <li key={beat.kicker}><span className="mono">0{index + 1}</span><div><b>{beat.title}</b><p>{beat.body}</p></div></li>)}
          </ol>
        </div>
      </section>
    );
  }

  return (
    <section className="research-scroll-story is-autoplay" id="journey" aria-labelledby="research-story-title" ref={sectionRef}>
      <div className="research-story-stage" data-film-state={filmFailed ? "poster" : filmReady ? "ready" : "loading"} data-playing={isPlaying && visible ? "true" : "false"}>
        {filmFailed ? (
          <img className="research-scroll-film" src={posterPath} alt="" aria-hidden="true" />
        ) : (
          <video
            className="research-scroll-film"
            ref={filmRef}
            src={filmPath}
            poster={posterPath}
            muted
            loop
            playsInline
            preload="auto"
            tabIndex={-1}
            aria-hidden="true"
            onLoadedData={handleFilmReady}
            onError={handleFilmError}
          />
        )}
        <div className="research-story-film-scrim" aria-hidden="true" />
        <div className="research-story-layout shell">
          <div className="research-story-copy">
            <div className="section-kicker"><span className="mono">A RESEARCH WORKFLOW THAT SHOWS ITS WORK</span><span className="kicker-line" /></div>
            <h1 id="research-story-title">From a claim to<br /><em>a result you can defend.</em></h1>
            <p className="research-story-intro">Bring a paper, a question, your code—or all three. EvoLab turns them into a researcher-approved experiment on your own machine, then explains what happened.</p>
            <OpenWorkspace className="button button-light story-primary-action">Open the EvoLab workspace <ArrowRight size={16} /></OpenWorkspace>
            <div className="research-story-beat-slot" aria-live={isPlaying ? "off" : "polite"} aria-atomic="true">
              <AnimatePresence mode="sync" initial={false}>
                <motion.div
                  className="research-story-beat"
                  key={activeBeat}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.14, ease: "easeOut" }}
                >
                  <span className="mono research-story-kicker">{beats[activeBeat].kicker}</span>
                  <h2>{beats[activeBeat].title}</h2>
                  <p>{beats[activeBeat].body}</p>
                </motion.div>
              </AnimatePresence>
            </div>
            <nav className="research-story-nav" aria-label="Choose a research-story stage">
              {beats.map((beat, index) => (
                <BeatButton key={beat.kicker} index={index} activeBeat={activeBeat} progress={progress} onSelect={() => selectBeat(index)} />
              ))}
            </nav>
            <div className="research-story-play-row">
              <button className="research-story-toggle" type="button" onClick={togglePlayback} aria-label={isPlaying ? "Pause the 3D story" : "Resume the 3D story"} aria-pressed={isPlaying}>
                {isPlaying ? <Pause size={13} aria-hidden="true" /> : <Play size={13} aria-hidden="true" />}
                {isPlaying ? "Pause motion" : "Resume motion"}
              </button>
              <span className="research-story-motion-status" role="status">{isPlaying && visible ? "AUTO-PLAYING · SILENT" : "PAUSED · SELECT A STAGE OR RESUME"}</span>
            </div>
          </div>
          <GraphScene
            activeBeat={activeBeat}
            reducedMotion={false}
            claimPath={claimPath}
            evidencePath={evidencePath}
            planPath={planPath}
            branchPath={branchPath}
            reportPath={reportPath}
            rotateX={rotateX}
            rotateY={rotateY}
            rotateZ={rotateZ}
            scale={scale}
            depth={depth}
          />
        </div>
      </div>
    </section>
  );
}
