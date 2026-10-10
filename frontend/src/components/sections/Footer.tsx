"use client";

import * as React from "react";
import Link from "next/link";
import { Container } from "@/components/ui";

export function Footer() {
  return (
    <footer className="border-t border-border-subtle bg-canvas-subtle/40 pt-16 pb-12 relative overflow-hidden">
      {/* Hero-matched Subtle Caustic Ambient Glow */}
      <div className="absolute bottom-0 left-1/4 w-96 h-32 bg-cyan/5 rounded-full blur-3xl pointer-events-none" />
      <div className="absolute bottom-0 right-1/4 w-96 h-32 bg-amber/5 rounded-full blur-3xl pointer-events-none" />

      <Container className="relative z-10">
        {/* Main Footer Columns: 4 columns on desktop, 2 on tablet, stacked on mobile */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-10 pb-16">
          {/* Column 1: Brand & Tagline */}
          <div className="sm:col-span-2 lg:col-span-1 pr-4">
            <Link href="/" className="inline-flex items-center gap-2.5 mb-4 group focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan/50 rounded-btn">
              <div className="w-7 h-7 rounded-btn bg-canvas-elevated border border-border-medium flex items-center justify-center group-hover:border-cyan/50 transition-colors">
                <span className="w-2.5 h-2.5 rounded-full bg-cyan shadow-[0_0_8px_rgba(56,189,248,0.8)]" />
              </div>
              <span className="font-semibold tracking-tight text-foreground text-lg">
                EvoLab
              </span>
            </Link>
            <p className="text-sm text-foreground-muted leading-relaxed">
              From paper to proof, on your own laptop.
            </p>
          </div>

          {/* Column 2: Product */}
          <div>
            <h4 className="font-mono text-xs uppercase tracking-wider text-foreground-faint mb-4">
              Product
            </h4>
            <ul className="space-y-3 text-sm">
              <li>
                <a
                  href="#how-it-works"
                  className="text-foreground-secondary hover:text-cyan-highlight transition-colors focus-visible:outline-none focus-visible:underline"
                >
                  How it works
                </a>
              </li>
              <li>
                <a
                  href="#entry-paths"
                  className="text-foreground-secondary hover:text-cyan-highlight transition-colors focus-visible:outline-none focus-visible:underline"
                >
                  Entry paths
                </a>
              </li>
              <li>
                <a
                  href="#report"
                  className="text-foreground-secondary hover:text-cyan-highlight transition-colors focus-visible:outline-none focus-visible:underline"
                >
                  Report
                </a>
              </li>
            </ul>
          </div>

          {/* Column 3: Get Started */}
          <div>
            <h4 className="font-mono text-xs uppercase tracking-wider text-foreground-faint mb-4">
              Get started
            </h4>
            <ul className="space-y-3 text-sm">
              <li>
                <Link
                  href="/dashboard"
                  className="text-foreground-secondary hover:text-cyan-highlight transition-colors inline-flex items-center gap-1.5 focus-visible:outline-none focus-visible:underline"
                >
                  <span>Open dashboard</span>
                  <span className="text-xs font-mono text-cyan-highlight">→</span>
                </Link>
              </li>
            </ul>
          </div>

          {/* Column 4: Project */}
          <div>
            <h4 className="font-mono text-xs uppercase tracking-wider text-foreground-faint mb-4">
              Project
            </h4>
            <ul className="space-y-3 text-sm">
              <li>
                <Link
                  href="/about"
                  className="text-foreground-secondary hover:text-cyan-highlight transition-colors focus-visible:outline-none focus-visible:underline"
                >
                  About
                </Link>
              </li>
              <li>
                <Link
                  href="/contact"
                  className="text-foreground-secondary hover:text-cyan-highlight transition-colors focus-visible:outline-none focus-visible:underline"
                >
                  Contact
                </Link>
              </li>
            </ul>
          </div>
        </div>

        {/* Bottom Bar */}
        <div className="pt-8 border-t border-border-subtle flex flex-col sm:flex-row items-center justify-between gap-4 font-mono text-xs text-foreground-faint">
          <div>
            © 2026 EvoLab
          </div>
          <div>
            Built for [hackathon name]
          </div>
        </div>
      </Container>
    </footer>
  );
}
