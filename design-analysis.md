# EvoLab Landing Page: Reference Design Analysis

> Design Read: ML research and experiment engine for machine learning researchers and graduate students, with a confident, dark-mode, high-precision technical instrument language, leaning toward Tailwind CSS + Geist & JetBrains Mono + physics-driven restrained Motion.
> Dials: `DESIGN_VARIANCE: 7` | `MOTION_INTENSITY: 6` | `VISUAL_DENSITY: 5`
> Rule Check: Zero em-dashes across all copy and tokens (Taste Skill Section 9.G compliance).

---

## 1. Reference Video Analysis & Aesthetic Deconstruction

Reference source: `hf_20260806_133255_956f653f-5d80-4b06-abd5-0f46c98b60fa.mp4`

### 1.1 The Visual Core & Mood
The reference video centers on an optical, high-precision gravitational/refractive lens phenomenon set against an infinite dark void.
- **Physicality:** Thick refractive dark glass / optic torus with intense internal refraction, physical weight, and glossy highlights.
- **Lighting Dynamics:** Dual-temperature light architecture. One side features a sharp, electric glacial cyan/blue arc reflection (`#38bdf8`), while the opposite flank captures a warm solar amber/golden caustic flare (`#f59e0b`).
- **Atmosphere:** Deep obsidian backdrop (`#050608` to `#090a0f`), with chromatic dispersion along refractive thresholds and zero oversaturated neon slop.
- **Overall Mood:** High-energy scientific laboratory instrument. Confident, mathematically rigorous, cinematic, and decidedly non-corporate. It evokes an advanced compute accelerator or particle collider interface rather than generic SaaS marketing.

---

## 2. Layout & Section Architecture

To match the structure, polish, and cadence of the reference while delivering EvoLab's unique product narrative, the landing page is architected into 7 distinct sections:

1. **Global Navigation (Sticky 68px Header):**
   - Left: EvoLab geometric wordmark with live status pill (`Autonomous Engine`).
   - Center: Precision anchors (`Architecture`, `Pipeline`, `Team Evolution`, `Benchmarks`).
   - Right: Quick links (`GitHub Repo`, `Start a Run` primary action).
   - Constraint: Strict single-line layout at desktop; height capped at 68px.

2. **Hero Section (Initial Viewport Lock):**
   - Height: `min-h-[100dvh]` (no mobile jumpiness).
   - Top padding: Capped at `pt-20` to `pt-24` desktop to keep all critical copy and CTAs above the fold.
   - Background: Looping refractive optical lens video with a radial vignette overlay blending into `#060709`.
   - Stack:
     - Eyebrow: `AUTONOMOUS SCIENTIFIC INVESTIGATION`
     - Headline (max 2 lines): `Drop in a paper. Get back an executable verdict.`
     - Subtext (19 words): `EvoLab turns papers, codebases, or questions into verified plans, runs experiments locally, and explains every result discrepancy.`
     - Action Pair: Primary `Start a Run` (solid high-contrast glacial glow) + Secondary `Inspect Architecture` (frosted glass border).
     - Interactive Intake Teaser: 4 convergent input badges (`Paper`, `Question`, `Codebase`, `Dataset`) routing toward the central controller.

3. **Problem & Diagnostic Strip:**
   - 3-column asymmetric split with micro-borders:
     - `01 / API Drift`: Deprecated dependencies break historical baselines silently.
     - `02 / Method Gaps`: Crucial hyperparameter ranges and seeds omitted from publication drafts.
     - `03 / Mutation Amnesia`: Manual trial-and-error code changes leave zero replayable provenance.

4. **Pipeline Flow (The 6-Stage Autonomous Run):**
   - Six sequential execution nodes connected by technical conduits and return loops:
     - `Stage 1: Intake & Entity Extraction`
     - `Stage 2: Plan Generation & Graph Draft`
     - `Stage 3: Local Sandbox Execution (Jailed Worker)`
     - `Stage 4: Automated Verification & Failure Debug`
     - `Stage 5: Hypothesis Branching & What-If Trees`
     - `Stage 6: Differential Report & Memory Consolidation`
   - Three return loops: Plan Revision, Self-Healing Debugger, and Parameter Sweep.

5. **Dynamic Team & Meta-Controller:**
   - Visualizing the 9 specialized research agent roles orchestrated by the Meta-Controller:
     - Literature Analyst, Hypothesis Formulator, Code Auditor, Sandbox Runner, Metric Evaluator, Forensic Debugger, Drift Sentinel, Memory Scribe, and the central Meta-Controller.
   - Capability-gap ladder showing autonomous agent specialization and probation rules.

6. **Evidence & Live Decision Ledger (Demo Story):**
   - Interactive investigation timeline tracking the KAN vs MLP benchmark on tabular data:
     - Detected API drift in `pykan` -> Debugger triggered -> Spawned specialized KAN agent -> Unmasked leaky ID column -> Replay memory cached.
   - Transparent honesty badge: `Cached baselines and replays are explicitly flagged.`

7. **Call to Action & Technical Footer:**
   - Headline: `Your laptop. Your data. A lab that learns.`
   - Commands: Direct worker run curl snippet + CLI pairing token.
   - Footer: Strict minimalism, legal links, documentation reference, clean status indicator.

---

## 3. Grid & Spacing Rhythm

- **Base Unit:** 4px grid system (`0.25rem`).
- **Container Maximum Widths:**
  - Standard container: `max-w-7xl` (1280px) with `px-6 md:px-8`.
  - Focused content / hero copy: `max-w-4xl` (896px).
  - Editorial reading measure: `max-w-[65ch]`.
- **Vertical Spacing Cadence:**
  - Section padding: `py-24 md:py-32` (rhythmic, breathable, avoiding claustrophobia).
  - Component gap: `gap-6 md:gap-8` for grids; `gap-3 md:gap-4` for button groups.
  - Section heading stack: `mb-12 md:mb-16`.

---

## 4. Typography System

- **Display & Headings:** `Geist Sans` (Variable, 300 to 800)
  - Hero Headline: `text-4xl sm:text-5xl lg:text-6xl font-semibold tracking-[-0.035em] leading-[1.08]`
  - Section Headlines: `text-2xl sm:text-3xl lg:text-4xl font-semibold tracking-[-0.03em] leading-[1.15]`
  - Subheadings: `text-lg sm:text-xl font-normal text-zinc-300 leading-relaxed`
- **Body Text:** `Geist Sans`
  - Base: `text-sm sm:text-base text-zinc-400 font-normal leading-relaxed`
  - Compact: `text-xs sm:text-sm text-zinc-400 font-normal leading-normal`
- **Technical & Data Elements:** `JetBrains Mono`
  - Eyebrows: `text-[11px] font-mono uppercase tracking-[0.18em] text-zinc-400`
  - Code / Terminal / Badges: `text-xs font-mono tracking-tight`
  - Metrics / Counters: `font-mono text-xl sm:text-2xl font-medium tracking-tight text-zinc-100`

---

## 5. Colour Palette (Exact Hex Values)

Derived from the optical video reference caustics and deep dark background:

### Background & Canvas Surfaces
- Canvas Deep Void: `#060709`
- Canvas Surface Raised: `#0b0d12`
- Card / Panel Surface: `#11141c`
- Elevated Layer / Hover: `#161b26`
- Popover / Dialog: `#1a202e`

### Borders & Hairlines
- Border Subtle: `rgba(255, 255, 255, 0.07)` (`#ffffff12`)
- Border Medium: `rgba(255, 255, 255, 0.12)` (`#ffffff1f`)
- Border Highlight / Active: `rgba(56, 189, 248, 0.35)` (Glacial Cyan trace)

### Primary Accent: Glacial Cyan (Optical Refraction Ring)
- Cyan 300: `#7dd3fc` (Text accents, glows)
- Cyan 400 (Core): `#38bdf8` (Primary brand accent, active states)
- Cyan 500: `#0ea5e9` (Buttons, highlights)
- Cyan 600: `#0284c7` (Hover states)
- Cyan Muted Glow: `rgba(56, 189, 248, 0.12)` (Backdrop lens tint)

### Secondary Accent: Solar Caustic Amber (Warm Flare Highlight)
- Amber 300: `#fcd34d`
- Amber 400 (Core): `#fbbf24` (Warning / trigger nodes, caustic warm edge)
- Amber 500: `#f59e0b`
- Amber Muted Glow: `rgba(245, 158, 11, 0.10)`

### Neutral Text Hierarchy
- Text Primary: `#f8fafc` (Zinc 50, crisp optical white)
- Text Secondary: `#cbd5e1` (Zinc 300, subheads, active links)
- Text Muted: `#94a3b8` (Zinc 400, body descriptions)
- Text Subtle: `#64748b` (Zinc 500, metadata, timestamps)

---

## 6. Motion, Easing & Interaction Physics

- **Motion Dial:** `MOTION_INTENSITY: 6`
- **Default Easing:** Physics spring and custom cubic curves:
  - Snappy UI transition: `cubic-bezier(0.16, 1, 0.3, 1)`
  - Smooth fluid pan: `cubic-bezier(0.25, 1, 0.5, 1)`
  - Spring profile: `{ stiffness: 220, damping: 24, mass: 0.8 }`
- **Tactile Button Feedback:**
  - Hover: subtle border illumination and `brightness(1.05)`
  - Active: `scale-[0.98]` physical tactile depression
- **Card Hover Elevation:**
  - Smooth `translate-y-[-2px]` with tinted border transition over 200ms
  - No oversaturated drop shadow slop; refined inner border highlight: `shadow-[inset_0_1px_0_rgba(255,255,255,0.08)]`
- **Reduced Motion:**
  - Complete `prefers-reduced-motion` override: transitions collapse to instant or pure opacity fade without coordinate shifts.

---

## 7. Component Style Rules

- **Buttons:**
  - Primary: High-contrast white/cyan solid with crisp black text, `rounded-lg`, `px-5 py-2.5`, `font-medium`, `text-sm`.
  - Secondary / Outline: `#11141c` base with `1px border-white/10`, hover border `border-cyan-400/40`, text `text-zinc-200`.
  - Ghost: Borderless, `text-zinc-400`, hover `text-zinc-100`, hover `bg-white/5`.
  - Height: Standard 40px; large 48px for hero actions.
- **Badges / Status Pills:**
  - Rounded: `rounded-full`
  - Style: Semi-transparent backdrop with 1px border (`bg-cyan-500/10 text-cyan-300 border-cyan-500/20`).
  - Text: `font-mono text-xs uppercase tracking-wider`.
- **Cards & Bento Panels:**
  - Corner Radius: Consistent `rounded-xl` (12px).
  - Background: `bg-[#0e1117]/80 backdrop-blur-md`.
  - Border: `1px solid rgba(255, 255, 255, 0.08)`.
  - Highlight: Inner top edge bevel `shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]`.
- **Navigation:**
  - Fixed / sticky top blur bar, height `68px`.
  - Background: `bg-[#060709]/80 backdrop-blur-xl border-b border-white/[0.06]`.
  - Single line layout across all desktop viewports.
