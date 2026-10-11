import type { Metadata } from "next";
import "./globals.css";

// Each area brings its own type and colour: the landing page (landing.css, dark) and the
// workspace (workspace.css). The root only sets the document defaults.
export const metadata: Metadata = {
  title: "EvoLab | Autonomous Research Environment",
  description:
    "EvoLab turns papers, codebases, and datasets into verified research plans, executes them on your laptop, and explains why results differ.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
