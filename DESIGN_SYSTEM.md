# EvoLab Design System (v0.1)

> Design Read: ML research and experiment engine for machine learning researchers and graduate students, with a confident, dark-mode, high-precision technical instrument language, leaning toward Tailwind CSS + Geist & JetBrains Mono + physics-driven restrained Motion.
> Dials: `DESIGN_VARIANCE: 7` | `MOTION_INTENSITY: 6` | `VISUAL_DENSITY: 5`
> Rule Check: Zero em-dashes across all copy and tokens (Taste Skill Section 9.G compliance).

---

## 1. Palette Tokens

Derived from the optical caustics and deep space black of the reference video:

### Canvas & Surface Hierarchy
| Token Name | CSS Variable | Hex / RGBA | Role |
|---|---|---|---|
| Canvas Void | `--canvas-void` | `#060709` | Deepest background canvas (default) |
| Canvas Subtle | `--canvas-subtle` | `#0b0d12` | Sub-section backgrounds & headers |
| Canvas Elevated | `--canvas-elevated` | `#11141c` | Active controls, input wells |
| Card Material | `--card-bg` | `rgba(17, 20, 28, 0.75)` | Frosted glass panels with blur |
| Card Hover | `--card-hover` | `rgba(22, 27, 38, 0.85)` | Elevated panel hover state |

### Accent Architecture
| Token Name | CSS Variable | Hex / RGBA | Role |
|---|---|---|---|
| Glacial Cyan Core | `--cyan-core` | `#38bdf8` | Primary brand accent & active states |
| Glacial Cyan Dim | `--cyan-dim` | `#0284c7` | Dark borders & pressed states |
| Glacial Cyan Glow | `--cyan-glow` | `rgba(56, 189, 248, 0.14)` | Radial caustic backdrops |
| Solar Amber Core | `--amber-core` | `#f59e0b` | Secondary accent, warnings, triggers |
| Solar Amber Dim | `--amber-dim` | `#b45309` | Subdued warnings & historical markers |
| Solar Amber Glow | `--amber-glow` | `rgba(245, 158, 11, 0.12)` | Warm flare highlight |

### Text & Neutral Hierarchy
| Token Name | CSS Variable | Hex Value | Role |
|---|---|---|---|
| Text Primary | `--text-primary` | `#f8fafc` | Main headings & key numbers |
| Text Secondary | `--text-secondary` | `#cbd5e1` | Subtitles & active navigation |
| Text Muted | `--text-muted` | `#94a3b8` | Explanatory copy & descriptions |
| Text Faint | `--text-faint` | `#64748b` | Timestamps & metadata labels |

### Borders & Dividing Lines
| Token Name | CSS Variable | Value | Role |
|---|---|---|---|
| Border Subtle | `--border-subtle` | `rgba(255, 255, 255, 0.08)` | Default card & element outline |
| Border Medium | `--border-medium` | `rgba(255, 255, 255, 0.14)` | Hover borders & table dividers |
| Border Highlight | `--border-highlight` | `rgba(56, 189, 248, 0.35)` | Active selection & focus outlines |

---

## 2. Typography Tokens

- **Primary Sans:** `Geist Sans` (Variable)
  - Clean geometric sans without the generic Inter aesthetic.
- **Code & Metric Mono:** `JetBrains Mono`
  - High-precision readability for code, tokens, budgets, and status badges.

### Scale & Tracking Matrix
| Level | Font Size | Line Height | Tracking | Weight |
|---|---|---|---|---|
| Hero Display | `3.75rem` (60px) | `1.08` | `-0.035em` | 600 (Semibold) |
| Section Headline | `2.25rem` (36px) | `1.15` | `-0.03em` | 600 (Semibold) |
| Subheading | `1.25rem` (20px) | `1.4` | `-0.015em` | 400 (Regular) |
| Body Regular | `0.9375rem` (15px) | `1.6` | `0` | 400 (Regular) |
| Technical Label | `0.6875rem` (11px) | `1.2` | `+0.18em` | 500 (Mono Medium, Uppercase) |
| Code Snippet | `0.8125rem` (13px) | `1.45` | `-0.01em` | 400 (Mono Regular) |

---

## 3. Shape, Radii & Depth Tokens

Strict corner radius lock across the application:
- **Buttons & Small Controls:** `8px` (`--radius-btn`, `rounded-btn`)
- **Cards & Bento Panels:** `12px` (`--radius-card`, `rounded-card`)
- **Outer Modals & Hero Frames:** `16px` (`--radius-panel`, `rounded-panel`)
- **Status Pills & Chips:** `9999px` (`--radius-pill`, `rounded-full`)

### Elevation & Lighting
- **Inner Bevel (Optical Reflection):** `inset 0 1px 0 rgba(255, 255, 255, 0.08)`
- **Cyan Caustic Glow:** `0 0 24px -4px rgba(56, 189, 248, 0.28)`
- **Amber Caustic Glow:** `0 0 24px -4px rgba(245, 158, 11, 0.24)`
- **Card Depth:** `0 8px 32px -8px rgba(0, 0, 0, 0.6)`

---

## 4. Motion & Easing Curves

- **Spring Profile (Micro-interactions & Buttons):**
  - Curve: `cubic-bezier(0.16, 1, 0.3, 1)`
  - Tactile Depression: `scale-[0.98]` on `:active`
- **Fluid Motion (Scroll reveals & Transitions):**
  - Curve: `cubic-bezier(0.25, 1, 0.5, 1)`
  - Duration: `250ms` (standard) / `400ms` (hero transitions)
- **Reduced Motion Guarantee:**
  - Complete `@media (prefers-reduced-motion: reduce)` override disabling coordinate shifts and collapsing transitions to subtle alpha fades.

---

## 5. UI Component Primitives

The core `/components/ui` library consists of:
1. `Button`: Primary, Cyan, Secondary, Outline, and Ghost variants with tactile feedback.
2. `Badge`: Technical monospace pills with optional live pulsing status indicator.
3. `Card`: Frosted glass panels with inner-bevel highlights and interactive hover states.
4. `Section`: Consistent vertical rhythm (`py-20` to `py-28`) with optional blueprint grid background.
5. `Container`: Standard width constraints (`max-w-7xl`) preventing ultra-wide distortion.
6. `Nav`: 68px single-line navigation bar with brand anchor, links, and action button.
