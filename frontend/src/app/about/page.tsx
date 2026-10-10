import Link from "next/link";
import { ArrowLeft } from "lucide-react";

export default function AboutPage() {
  return (
    <main className="min-h-screen bg-canvas text-foreground p-8 flex flex-col justify-center items-center text-center">
      <div className="max-w-md p-8 rounded-panel bg-card border border-border-subtle shadow-card-depth">
        <h1 className="text-2xl font-semibold mb-3">About EvoLab</h1>
        <p className="text-sm text-foreground-secondary mb-6 leading-relaxed">
          From paper to proof, on your own laptop. EvoLab turns research questions, papers, codebases, and datasets into verified plans and honest reports.
        </p>
        <Link
          href="/"
          className="inline-flex items-center gap-2 text-sm text-cyan-highlight hover:underline"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Back to Home</span>
        </Link>
      </div>
    </main>
  );
}
