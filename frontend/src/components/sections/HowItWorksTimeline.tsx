"use client";

import * as React from "react";
import { Container, Section, Card } from "@/components/ui";
import { HOW_IT_WORKS_STEPS } from "@/content/landing";
import { CheckCircle2, Laptop, RefreshCw, FileText, ArrowRight } from "lucide-react";

export function HowItWorksTimeline() {
  const [activeStep, setActiveStep] = React.useState<number>(1);
  const containerRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    const handleScroll = () => {
      if (!containerRef.current) return;
      const elements = containerRef.current.querySelectorAll("[data-timeline-step]");
      const scrollPos = window.scrollY + window.innerHeight * 0.5;

      let current = 1;
      elements.forEach((el) => {
        const rect = el.getBoundingClientRect();
        const top = rect.top + window.scrollY;
        if (scrollPos >= top) {
          const stepNum = parseInt(el.getAttribute("data-timeline-step") || "1", 10);
          if (stepNum > current) current = stepNum;
        }
      });
      setActiveStep(current);
    };

    window.addEventListener("scroll", handleScroll, { passive: true });
    handleScroll();
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  const getStepMiniVisual = (step: number) => {
    switch (step) {
      case 1:
        return (
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-mono bg-cyan/15 text-cyan-highlight border border-cyan/30">
              Paper
            </span>
            <span className="text-foreground-faint text-xs">•</span>
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-mono bg-amber/15 text-amber-highlight border border-amber/30">
              Question
            </span>
            <span className="text-foreground-faint text-xs">•</span>
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-mono bg-cyan/15 text-cyan-highlight border border-cyan/30">
              Codebase
            </span>
            <span className="text-foreground-faint text-xs">•</span>
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-mono bg-amber/15 text-amber-highlight border border-amber/30">
              Dataset
            </span>
          </div>
        );
      case 2:
        return (
          <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-full text-[10px] font-mono bg-amber/15 text-amber-highlight border border-amber/30">
            <FileText className="w-3 h-3 text-amber-highlight" />
            <span>Brief ready</span>
          </div>
        );
      case 3:
        return (
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-mono bg-cyan/15 text-cyan-highlight border border-cyan/30">
              <CheckCircle2 className="w-2.5 h-2.5" /> Approve
            </span>
            <span className="text-foreground-faint text-xs">•</span>
            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-mono bg-white/[0.05] text-foreground-secondary border border-border-subtle">
              Edit
            </span>
            <span className="text-foreground-faint text-xs">•</span>
            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-mono bg-white/[0.05] text-foreground-secondary border border-border-subtle">
              Reject
            </span>
          </div>
        );
      case 4:
        return (
          <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-full text-[10px] font-mono bg-amber/15 text-amber-highlight border border-amber/30">
            <Laptop className="w-3 h-3 text-amber-highlight" />
            <span>Running locally</span>
          </div>
        );
      case 5:
        return (
          <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-full text-[10px] font-mono bg-cyan/15 text-cyan-highlight border border-cyan/30">
            <RefreshCw className="w-3 h-3 text-cyan-highlight" />
            <span>Plan updated</span>
          </div>
        );
      case 6:
        return (
          <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-full text-[10px] font-mono bg-amber/15 text-amber-highlight border border-amber/30">
            <CheckCircle2 className="w-3 h-3 text-amber-highlight" />
            <span>Report ready</span>
          </div>
        );
      default:
        return null;
    }
  };

  return (
    <Section id="how-it-works" spacing="spacious" className="border-t border-border-subtle bg-canvas">
      <Container>
        {/* Section Header */}
        <div className="max-w-3xl mx-auto text-center mb-20">
          <div className="mb-3">
            <span className="font-mono text-[11px] uppercase tracking-[0.18em] text-foreground-faint">
              Step by step
            </span>
          </div>
          <h2 className="text-3xl sm:text-4xl md:text-5xl font-semibold tracking-[-0.03em] text-foreground leading-[1.12] mb-4">
            How EvoLab works
          </h2>
          <p className="text-base sm:text-lg text-foreground-secondary leading-relaxed max-w-2xl mx-auto">
            From initial research material to verified proof on your machine, with complete transparency at every turn.
          </p>
        </div>

        {/* Timeline Container */}
        <div ref={containerRef} className="relative max-w-5xl mx-auto pt-6 pb-12">
          {/* Central Vertical Connector Line (Desktop) */}
          <div className="hidden md:block absolute left-1/2 top-4 bottom-12 w-[2px] -translate-x-1/2 bg-border-subtle z-0">
            {/* Scroll Glow Fill Line */}
            <div
              className="w-full bg-gradient-to-b from-cyan via-amber to-cyan transition-all duration-500 ease-out shadow-[0_0_8px_rgba(56,189,248,0.5)]"
              style={{
                height: `${Math.min(100, Math.max(8, ((activeStep - 0.5) / 5.5) * 100))}%`,
              }}
            />
          </div>

          {/* Left Vertical Line (Mobile) */}
          <div className="md:hidden absolute left-5 top-4 bottom-12 w-[2px] bg-border-subtle z-0">
            <div
              className="w-full bg-gradient-to-b from-cyan via-amber to-cyan transition-all duration-500 ease-out shadow-[0_0_8px_rgba(56,189,248,0.5)]"
              style={{
                height: `${Math.min(100, Math.max(8, ((activeStep - 0.5) / 5.5) * 100))}%`,
              }}
            />
          </div>

          {/* Timeline Nodes */}
          <div className="space-y-16 md:space-y-24 relative z-10">
            {HOW_IT_WORKS_STEPS.map((step) => {
              const isPassed = activeStep >= step.step;
              const isCurrent = activeStep === step.step;
              const isEven = step.step % 2 === 0;

              return (
                <div
                  key={step.step}
                  data-timeline-step={step.step}
                  className={`flex flex-col md:flex-row items-start md:items-center gap-6 md:gap-0 relative ${
                    isEven ? "md:flex-row-reverse" : ""
                  }`}
                >
                  {/* Card Half (Desktop alternating left/right) */}
                  <div
                    className={`w-full md:w-[calc(50%-40px)] pl-14 md:pl-0 ${
                      isEven ? "md:text-left" : "md:text-left"
                    }`}
                  >
                    <Card
                      className={`p-6 sm:p-7 relative transition-all duration-400 ${
                        isCurrent
                          ? "bg-card/95 border-cyan/50 shadow-glow-cyan"
                          : isPassed
                          ? "bg-card/80 border-border-medium shadow-card-depth"
                          : "bg-card/40 border-border-subtle opacity-75"
                      }`}
                    >
                      {/* Step Badge */}
                      <div className="flex items-center justify-between mb-3">
                        <span
                          className={`font-mono text-xs uppercase tracking-wider font-semibold ${
                            isCurrent
                              ? "text-cyan-highlight"
                              : isPassed
                              ? "text-foreground-secondary"
                              : "text-foreground-faint"
                          }`}
                        >
                          Step {step.step}
                        </span>
                        {/* Chip / Mini Visual */}
                        <div>{getStepMiniVisual(step.step)}</div>
                      </div>

                      {/* Title */}
                      <h3 className="text-lg sm:text-xl font-semibold text-foreground tracking-tight mb-2">
                        {step.title}
                      </h3>

                      {/* One Sentence Description (max 2 lines) */}
                      <p className="text-sm text-foreground-secondary leading-relaxed mb-4">
                        {step.sentence}
                      </p>

                      {/* Small Muted 'What you see' line */}
                      <div className="pt-3 border-t border-border-subtle flex items-start gap-2">
                        <span className="font-mono text-[11px] text-foreground-faint uppercase tracking-wider shrink-0 mt-0.5">
                          What you see:
                        </span>
                        <span className="text-xs text-foreground-muted leading-relaxed">
                          {step.whatYouSee}
                        </span>
                      </div>
                    </Card>
                  </div>

                  {/* Desktop Thin Curved Connector Line */}
                  <div className="hidden md:flex items-center justify-center w-[80px] shrink-0 h-10 relative">
                    <svg
                      className="w-full h-10 overflow-visible"
                      fill="none"
                      xmlns="http://www.w3.org/2000/svg"
                    >
                      {isEven ? (
                        <path
                          d="M 40 20 C 20 20, 10 20, 0 20"
                          stroke={isCurrent ? "var(--amber-core)" : isPassed ? "var(--cyan-dim)" : "var(--border-subtle)"}
                          strokeWidth="1.5"
                          strokeDasharray={isCurrent ? "none" : "3 3"}
                          className="transition-colors duration-400"
                        />
                      ) : (
                        <path
                          d="M 40 20 C 60 20, 70 20, 80 20"
                          stroke={isCurrent ? "var(--cyan-core)" : isPassed ? "var(--cyan-dim)" : "var(--border-subtle)"}
                          strokeWidth="1.5"
                          strokeDasharray={isCurrent ? "none" : "3 3"}
                          className="transition-colors duration-400"
                        />
                      )}
                    </svg>

                    {/* Central Glowing Node */}
                    <div
                      className={`absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-9 h-9 rounded-full border-2 flex items-center justify-center font-mono text-xs font-semibold transition-all duration-400 z-20 ${
                        isCurrent
                          ? "bg-canvas-elevated border-cyan text-cyan-highlight shadow-[0_0_18px_rgba(56,189,248,0.9)] scale-110"
                          : isPassed
                          ? "bg-canvas-elevated border-cyan/60 text-foreground shadow-[0_0_10px_rgba(56,189,248,0.3)]"
                          : "bg-canvas-subtle border-border-subtle text-foreground-faint"
                      }`}
                    >
                      {step.step}
                    </div>
                  </div>

                  {/* Mobile Node Icon (Positioned over left vertical line) */}
                  <div
                    className={`md:hidden absolute left-5 top-7 -translate-x-1/2 w-8 h-8 rounded-full border-2 flex items-center justify-center font-mono text-xs font-semibold transition-all duration-400 z-20 ${
                      isCurrent
                        ? "bg-canvas-elevated border-cyan text-cyan-highlight shadow-[0_0_14px_rgba(56,189,248,0.9)]"
                        : isPassed
                        ? "bg-canvas-elevated border-cyan/60 text-foreground"
                        : "bg-canvas-subtle border-border-subtle text-foreground-faint"
                    }`}
                  >
                    {step.step}
                  </div>

                  {/* Empty Spacer Half on Desktop */}
                  <div className="hidden md:block w-[calc(50%-40px)]" />
                </div>
              );
            })}
          </div>
        </div>
      </Container>
    </Section>
  );
}
