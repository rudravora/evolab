"use client";

import * as React from "react";
import { Container, Section, Card, Badge } from "@/components/ui";
import { SAMPLE_REPORT_ROWS, DIFFERENCE_ENTRIES } from "@/content/landing";
import { CheckCircle2, AlertCircle, FileText } from "lucide-react";

export function ReportSection() {
  const getVerdictBadge = (verdict: string) => {
    switch (verdict) {
      case "Reproduced":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-mono bg-cyan/15 text-cyan-highlight border border-cyan/30">
            <CheckCircle2 className="w-3.5 h-3.5" />
            <span>Reproduced</span>
          </span>
        );
      case "Baseline established":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-mono bg-white/[0.08] text-foreground-secondary border border-border-medium">
            <span>Baseline established</span>
          </span>
        );
      case "Partial":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-mono bg-amber/15 text-amber-highlight border border-amber/30">
            <AlertCircle className="w-3.5 h-3.5" />
            <span>Partial</span>
          </span>
        );
      case "Not reproduced":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-mono bg-red-500/15 text-red-400 border border-red-500/30">
            <span>Not reproduced</span>
          </span>
        );
      case "Exploratory":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-mono bg-purple-500/15 text-purple-300 border border-purple-500/30">
            <span>Exploratory</span>
          </span>
        );
      default:
        return null;
    }
  };

  return (
    <Section id="report" spacing="spacious" className="border-t border-border-subtle bg-canvas">
      <Container>
        {/* Section Header */}
        <div className="max-w-3xl mb-12">
          <div className="mb-3">
            <span className="font-mono text-[11px] uppercase tracking-[0.18em] text-foreground-faint">
              Scientific Interpretability
            </span>
          </div>
          <h2 className="text-3xl sm:text-4xl font-semibold tracking-[-0.03em] text-foreground leading-[1.15] mb-3">
            Reports that explain why results differ
          </h2>
          <p className="text-sm sm:text-base text-foreground-secondary leading-relaxed">
            Every run produces an honest comparison against published claims, with plain explanations whenever numbers diverge.
          </p>
        </div>

        {/* Report Card */}
        <Card className="p-6 sm:p-8 border-border-medium bg-card/90 shadow-card-depth">
          {/* Card Header with Sample Report badge */}
          <div className="flex flex-wrap items-center justify-between gap-4 pb-6 border-b border-border-subtle mb-6">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-btn bg-canvas-elevated border border-border-medium flex items-center justify-center">
                <FileText className="w-4 h-4 text-cyan-highlight" />
              </div>
              <div>
                <h3 className="text-lg font-semibold text-foreground tracking-tight">
                  Sample Research Report
                </h3>
                <span className="text-xs text-foreground-muted">
                  Direct evaluation against publication claims
                </span>
              </div>
            </div>

            {/* Clear 'Sample report' Badge */}
            <div>
              <Badge variant="cyan" dot className="font-mono text-xs px-3 py-1">
                Sample report
              </Badge>
            </div>
          </div>

          {/* 3-Row Comparison Table */}
          <div className="overflow-x-auto mb-8">
            <table className="w-full text-left font-mono text-xs sm:text-sm border-collapse min-w-[560px]">
              <thead>
                <tr className="border-b border-border-medium text-foreground-faint uppercase tracking-wider text-[11px]">
                  <th className="py-3 px-3">Target</th>
                  <th className="py-3 px-3">Paper claim</th>
                  <th className="py-3 px-3">Your run</th>
                  <th className="py-3 px-3">Delta</th>
                  <th className="py-3 px-3 text-right">Verdict</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-subtle text-foreground-secondary">
                {SAMPLE_REPORT_ROWS.map((row, idx) => (
                  <tr key={idx} className="hover:bg-white/[0.02] transition-colors">
                    <td className="py-3.5 px-3 font-sans font-medium text-foreground">
                      {row.target}
                    </td>
                    <td className="py-3.5 px-3 text-foreground-muted">{row.paperClaim}</td>
                    <td className="py-3.5 px-3 text-foreground font-semibold">{row.yourRun}</td>
                    <td
                      className={`py-3.5 px-3 font-semibold ${
                        row.verdict === "Partial"
                          ? "text-amber-highlight"
                          : "text-cyan-highlight"
                      }`}
                    >
                      {row.delta}
                    </td>
                    <td className="py-3.5 px-3 text-right">{getVerdictBadge(row.verdict)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Why Results Differ Section */}
          <div className="pt-6 border-t border-border-subtle">
            <h4 className="text-base font-semibold text-foreground tracking-tight mb-4">
              Why results differ
            </h4>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {DIFFERENCE_ENTRIES.map((entry, idx) => (
                <div
                  key={idx}
                  className="p-5 rounded-card bg-canvas-elevated/80 border border-border-subtle space-y-2.5"
                >
                  <h5 className="font-semibold text-sm text-foreground">
                    {entry.title}
                  </h5>
                  <p className="text-xs sm:text-sm text-foreground-muted leading-relaxed">
                    <strong className="text-foreground-secondary font-medium">What we found: </strong>
                    {entry.whatWeFound}
                  </p>
                  <p className="text-xs sm:text-sm text-foreground-muted leading-relaxed">
                    <strong className="text-foreground-secondary font-medium">What changed: </strong>
                    {entry.whatChanged}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </Card>

        {/* Caption underneath the card */}
        <p className="text-xs text-foreground-muted text-center mt-4">
          Illustrative example. Real reports are generated from your own runs.
        </p>
      </Container>
    </Section>
  );
}
