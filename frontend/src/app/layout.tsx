import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "EvoLab | Autonomous Research Environment",
  description:
    "EvoLab turns papers, codebases, and datasets into verified research plans, executes them on your laptop, and explains why results differ.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark" data-theme="dark">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Geist:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;600&family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="bg-canvas text-foreground font-sans antialiased selection:bg-cyan/20 selection:text-cyan-highlight">
        {children}
      </body>
    </html>
  );
}
