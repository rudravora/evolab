"use client";

import * as React from "react";
import { Container, Section, Card, Badge } from "@/components/ui";
import { ENTRY_PATHS } from "@/content/landing";
import { FileText, Code2, Database, HelpCircle, CheckCircle2, Compass, Layers } from "lucide-react";

export function EntryPathsSection() {
  const getIcon = (name: string) => {
    switch (name) {
      case "FileText":
        return <FileText className="w-5 h-5 text-cyan-highlight" />;
      case "Code2":
        return <Code2 className="w-5 h-5 text-cyan-highlight" />;
      case "Database":
        return <Database className="w-5 h-5 text-amber-highlight" />;
      case "HelpCircle":
        return <HelpCircle className="w-5 h-5 text-amber-highlight" />;
      default:
        return null;
    }
  };

  const getVerdictBadge = (verdict: string) => {
    switch (verdict) {
      case "reproduced":
        return (
          <Badge variant="cyan" dot className="text-[10px]">
            reproduced
          </Badge>
        );
      case "baseline_established":
        return (
          <Badge variant="neutral" dot className="text-[10px]">
            baseline_established
          </Badge>
        );
      case "exploratory":
        return (
          <Badge variant="amber" dot className="text-[10px]">
            exploratory
          </Badge>
        );
      default:
        return null;
    }
  };

  return (
    <Section id="entry-paths" spacing="normal" className="border-t border-border-subtle bg-canvas-subtle/50">
      <Container>
        {/* Section Header */}
        <div className="max-w-2xl mb-12">
          <div className="mb-3">
            <span className="font-mono text-[11px] uppercase tracking-[0.18em] text-foreground-faint">
              Four Entry Paths
            </span>
          </div>
          <h2 className="text-3xl sm:text-4xl font-semibold tracking-[-0.03em] text-foreground leading-[1.15] mb-3">
            Start from any research artefact
          </h2>
          <p className="text-sm sm:text-base text-foreground-secondary leading-relaxed">
            Provide any single input or combine all four. EvoLab adapts to match available materials and returns a typed verdict.
          </p>
        </div>

        {/* 4 Cards Bento Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5">
          {ENTRY_PATHS.map((item) => (
            <Card
              key={item.id}
              hoverable
              className="flex flex-col justify-between group p-6 bg-card/70 hover:bg-card-hover border-border-subtle hover:border-border-medium transition-all"
            >
              <div>
                <div className="flex items-center justify-between mb-4">
                  <div className="w-10 h-10 rounded-btn bg-canvas-elevated border border-border-medium flex items-center justify-center group-hover:border-cyan/40 transition-colors">
                    {getIcon(item.iconName)}
                  </div>
                  {getVerdictBadge(item.verdict)}
                </div>

                <h3 className="text-base font-semibold text-foreground mb-2 group-hover:text-cyan-highlight transition-colors">
                  {item.title}
                </h3>

                <p className="text-xs sm:text-sm text-foreground-muted leading-relaxed mb-6">
                  {item.summary}
                </p>
              </div>

              {/* Bottom Target Indicator */}
              <div className="pt-4 border-t border-border-subtle flex items-center justify-between font-mono text-[11px] text-foreground-faint">
                <span>Output Contract</span>
                <span className="text-foreground-secondary">{item.verdict}</span>
              </div>
            </Card>
          ))}
        </div>
      </Container>
    </Section>
  );
}
