import { Nav } from "@/components/ui";
import {
  HeroSection,
  EntryPathsSection,
  HowItWorksTimeline,
  ReportSection,
  EvolutionSection,
  Footer,
} from "@/components/sections";

export default function Home() {
  return (
    <main className="min-h-screen bg-canvas text-foreground selection:bg-cyan/20 selection:text-cyan-highlight">
      {/* 1. Global Navigation */}
      <Nav />

      {/* 2. Hero Section with Input Chips -> Research Brief */}
      <HeroSection />

      {/* 3. Four Entry Paths */}
      <EntryPathsSection />

      {/* 4. How EvoLab Works: Scroll-driven Timeline */}
      <HowItWorksTimeline />

      {/* 5. Explanatory Reports: Sample Report Preview */}
      <ReportSection />

      {/* 6. Continuous Evolution */}
      <EvolutionSection />

      {/* 7. Comprehensive Proper Footer */}
      <Footer />
    </main>
  );
}
