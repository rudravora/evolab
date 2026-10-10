"use client";

import * as React from "react";
import Link from "next/link";
import { Container, Button, Badge } from "@/components/ui";
import { HERO_CONTENT } from "@/content/landing";
import { ArrowRight, Play, FileText, HelpCircle, Code2, Database } from "lucide-react";

export function HeroSection() {
  const getChipIcon = (id: string) => {
    switch (id) {
      case "paper":
        return <FileText className="w-4 h-4 text-cyan-highlight" />;
      case "question":
        return <HelpCircle className="w-4 h-4 text-amber-highlight" />;
      case "codebase":
        return <Code2 className="w-4 h-4 text-cyan-highlight" />;
      case "dataset":
        return <Database className="w-4 h-4 text-amber-highlight" />;
      default:
        return null;
    }
  };

  return (
    <section className="relative min-h-[100dvh] flex flex-col justify-between pt-24 pb-12 overflow-hidden bg-canvas">
      {/* Background Video Layer with Optical Flare */}
      <div className="absolute inset-0 z-0 overflow-hidden pointer-events-none opacity-45">
        <video
          autoPlay
          loop
          muted
          playsInline
          className="w-full h-full object-cover object-center filter saturate-150 contrast-125"
        >
          <source src="/hero-reference.mp4" type="video/mp4" />
        </video>
        <div className="absolute inset-0 bg-gradient-to-b from-canvas/90 via-canvas/60 to-canvas" />
        <div className="absolute inset-0 bg-radial-vignette opacity-80" />
      </div>

      {/* Blueprint Grid Watermark */}
      <div className="absolute inset-0 bg-grid-pattern opacity-40 z-0 pointer-events-none" />

      {/* Hero Copy Container */}
      <Container className="relative z-10 my-auto">
        <div className="max-w-4xl mx-auto text-center flex flex-col items-center">
          {/* Headline (Max 2 lines desktop) */}
          <h1 className="text-4xl sm:text-5xl md:text-6xl font-semibold tracking-[-0.035em] leading-[1.08] text-foreground mb-5 text-balance">
            {HERO_CONTENT.headline}
          </h1>

          {/* Subline (Max 20 words) */}
          <p className="text-base sm:text-lg text-foreground-secondary leading-relaxed max-w-[65ch] mb-8 text-balance">
            {HERO_CONTENT.subline}
          </p>

          {/* Action Pair */}
          <div className="flex flex-wrap items-center justify-center gap-3.5 mb-14">
            <Link
              href="/dashboard"
              className="inline-flex items-center justify-center h-12 px-6 text-base rounded-btn font-semibold bg-cyan text-canvas hover:bg-cyan-highlight transition-all shadow-glow-cyan gap-2.5 group"
            >
              <span>{HERO_CONTENT.primaryCta}</span>
              <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
            </Link>
            <a
              href="#how-it-works"
              className="inline-flex items-center justify-center h-12 px-6 text-base rounded-btn font-medium bg-canvas-elevated text-foreground border border-border-subtle hover:border-cyan/40 hover:bg-card-hover hover:text-foreground transition-all gap-2.5 group"
            >
              <Play className="w-3.5 h-3.5 fill-current text-foreground-muted group-hover:text-foreground transition-colors" />
              <span>{HERO_CONTENT.secondaryCta}</span>
            </a>
          </div>

          {/* Animated 4-Input Convergence Canvas */}
          <div className="w-full max-w-3xl relative mt-2 pt-6">
            <div className="relative p-6 sm:p-8 rounded-panel bg-card/60 backdrop-blur-xl border border-border-subtle shadow-card-depth">
              {/* Outer Glow Halo */}
              <div className="absolute -inset-0.5 bg-gradient-to-r from-cyan/20 via-transparent to-amber/20 rounded-panel opacity-40 blur-xl pointer-events-none" />

              {/* 4 Converging Input Chips */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-8 relative z-10">
                {HERO_CONTENT.chips.map((chip) => (
                  <div
                    key={chip.id}
                    className="flex flex-col items-start p-3 rounded-card bg-canvas-elevated/80 border border-border-subtle hover:border-border-medium transition-all group"
                  >
                    <div className="flex items-center gap-2 mb-1.5">
                      {getChipIcon(chip.id)}
                      <span className="font-semibold text-xs text-foreground group-hover:text-cyan-highlight transition-colors">
                        {chip.label}
                      </span>
                    </div>
                    <span className="font-mono text-[10px] text-foreground-faint uppercase tracking-wider">
                      {chip.format}
                    </span>
                  </div>
                ))}
              </div>

              {/* SVG Convergence Data Conduits */}
              <div className="relative h-12 w-full flex items-center justify-center my-1">
                <svg
                  className="w-full h-12 stroke-border-medium overflow-visible"
                  fill="none"
                  xmlns="http://www.w3.org/2000/svg"
                >
                  {/* Left lines converging to center */}
                  <path
                    d="M 120 0 C 120 24, 340 12, 384 48"
                    strokeWidth="1.5"
                    strokeDasharray="4 4"
                    className="opacity-60"
                  />
                  <path
                    d="M 260 0 C 260 20, 360 20, 384 48"
                    strokeWidth="1.5"
                    stroke="var(--cyan-core)"
                    className="opacity-70"
                  />
                  {/* Right lines converging to center */}
                  <path
                    d="M 500 0 C 500 20, 410 20, 384 48"
                    strokeWidth="1.5"
                    stroke="var(--amber-core)"
                    className="opacity-70"
                  />
                  <path
                    d="M 640 0 C 640 24, 430 12, 384 48"
                    strokeWidth="1.5"
                    strokeDasharray="4 4"
                    className="opacity-60"
                  />
                </svg>
              </div>

              {/* Central Glowing Research Brief Node */}
              <div className="relative z-10 flex flex-col items-center">
                <div className="inline-flex items-center gap-3 px-5 py-2.5 rounded-card bg-canvas-elevated border border-cyan/40 shadow-glow-cyan">
                  <div className="w-2.5 h-2.5 rounded-full bg-cyan shadow-[0_0_10px_rgba(56,189,248,1)] animate-ping" />
                  <div className="text-left">
                    <span className="font-semibold text-xs tracking-tight text-foreground block">
                      Research Brief
                    </span>
                    <span className="font-mono text-[10px] text-foreground-muted">
                      Ready to plan
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </Container>
    </section>
  );
}
