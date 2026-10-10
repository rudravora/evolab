"use client";

import * as React from "react";
import { Container, Section, Card } from "@/components/ui";
import { EVOLUTION_POINTS } from "@/content/landing";
import { History, Wrench, ShieldCheck } from "lucide-react";

export function EvolutionSection() {
  const getIcon = (idx: number) => {
    switch (idx) {
      case 0:
        return <History className="w-5 h-5 text-cyan-highlight" />;
      case 1:
        return <Wrench className="w-5 h-5 text-amber-highlight" />;
      case 2:
        return <ShieldCheck className="w-5 h-5 text-cyan-highlight" />;
      default:
        return null;
    }
  };

  return (
    <Section id="evolution" spacing="normal" className="border-t border-border-subtle bg-canvas-subtle/30">
      <Container>
        {/* Section Header */}
        <div className="max-w-2xl mx-auto text-center mb-12">
          <div className="mb-3">
            <span className="font-mono text-[11px] uppercase tracking-[0.18em] text-foreground-faint">
              Continuous Improvement
            </span>
          </div>
          <h2 className="text-3xl sm:text-4xl font-semibold tracking-[-0.03em] text-foreground leading-[1.15] mb-3">
            It gets better with every run
          </h2>
          <p className="text-sm sm:text-base text-foreground-secondary leading-relaxed">
            Every run compounds. EvoLab preserves what worked, adopts new tools when needed, and always asks for your confirmation.
          </p>
        </div>

        {/* 3 Compact High-Level Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 max-w-5xl mx-auto">
          {EVOLUTION_POINTS.map((point, idx) => (
            <Card
              key={point.title}
              hoverable
              className="p-6 bg-card/70 hover:bg-card-hover border-border-subtle hover:border-border-medium transition-all flex flex-col justify-between"
            >
              <div>
                <div className="w-10 h-10 rounded-btn bg-canvas-elevated border border-border-medium flex items-center justify-center mb-4">
                  {getIcon(idx)}
                </div>
                <h3 className="text-base font-semibold text-foreground tracking-tight mb-2">
                  {point.title}
                </h3>
                <p className="text-sm text-foreground-muted leading-relaxed">
                  {point.description}
                </p>
              </div>

              <div className="pt-4 mt-6 border-t border-border-subtle/60 flex items-center justify-between font-mono text-[11px] text-foreground-faint">
                <span>0{idx + 1}</span>
                <span className="text-foreground-secondary">Always in your hands</span>
              </div>
            </Card>
          ))}
        </div>
      </Container>
    </Section>
  );
}
