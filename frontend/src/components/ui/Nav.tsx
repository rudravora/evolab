"use client";

import * as React from "react";
import Link from "next/link";
import { cn } from "@/lib/utils";

export interface NavProps {
  className?: string;
}

export const Nav: React.FC<NavProps> = ({ className }) => {
  const [scrolled, setScrolled] = React.useState(false);

  React.useEffect(() => {
    const handleScroll = () => {
      setScrolled(window.scrollY > 16);
    };
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  return (
    <header
      className={cn(
        "fixed top-0 left-0 right-0 z-50 h-[68px] transition-all duration-200 ease-smooth",
        scrolled
          ? "bg-canvas/80 backdrop-blur-xl border-b border-border-subtle shadow-card-depth"
          : "bg-transparent border-b border-transparent",
        className
      )}
    >
      <div className="max-w-7xl mx-auto h-full px-5 sm:px-6 md:px-8 flex items-center justify-between">
        {/* Brand Lockup (Local Run badge removed) */}
        <Link href="/" className="flex items-center gap-2.5 group">
          <div className="w-7 h-7 rounded-btn bg-canvas-elevated border border-border-medium flex items-center justify-center group-hover:border-cyan/50 transition-colors">
            <span className="w-2.5 h-2.5 rounded-full bg-cyan shadow-[0_0_8px_rgba(56,189,248,0.8)]" />
          </div>
          <span className="font-semibold tracking-tight text-foreground text-base">
            EvoLab
          </span>
        </Link>

        {/* Desktop Navigation Links */}
        <nav className="hidden md:flex items-center gap-8 text-sm text-foreground-secondary">
          <a
            href="#how-it-works"
            className="hover:text-cyan-highlight transition-colors focus-visible:outline-none focus-visible:underline"
          >
            How it works
          </a>
          <a
            href="#entry-paths"
            className="hover:text-cyan-highlight transition-colors focus-visible:outline-none focus-visible:underline"
          >
            Entry paths
          </a>
          <a
            href="#report"
            className="hover:text-cyan-highlight transition-colors focus-visible:outline-none focus-visible:underline"
          >
            Report
          </a>
        </nav>

        {/* Login & Sign Up Actions */}
        <div className="flex items-center gap-3">
          <Link
            href="/login"
            className="inline-flex items-center justify-center h-9 px-3.5 rounded-btn text-xs font-medium text-foreground-secondary hover:text-foreground hover:bg-white/[0.05] transition-all"
          >
            Login
          </Link>
          <Link
            href="/signup"
            className="inline-flex items-center justify-center h-9 px-4 rounded-btn text-xs font-semibold bg-cyan text-canvas hover:bg-cyan-highlight transition-all shadow-glow-cyan"
          >
            Sign up
          </Link>
        </div>
      </div>
    </header>
  );
};
