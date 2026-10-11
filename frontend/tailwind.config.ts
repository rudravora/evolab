import type { Config } from "tailwindcss";

// Tailwind is used by the workspace pages (dashboard, runs, agents, memory). The landing page
// uses its own stylesheet (src/app/landing.css).
const config: Config = {
  content: ["./src/app/**/*.{js,ts,jsx,tsx,mdx}", "./src/components/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    screens: {
      sm: "640px",
      md: "768px",
      lg: "1024px",
      xl: "1280px",
      "2xl": "1400px",
    },
    extend: {
      colors: {
        // Workspace tokens (prefix v2). Values live in src/app/(workspace)/workspace.css as RGB
        // triplets on the .v2 wrapper, so opacity modifiers work and light/dark follow the system.
        v2: {
          bg: "rgb(var(--v2-bg) / <alpha-value>)",
          surface: "rgb(var(--v2-surface) / <alpha-value>)",
          raised: "rgb(var(--v2-raised) / <alpha-value>)",
          fill: "rgb(var(--v2-fill) / <alpha-value>)",
          line: "rgb(var(--v2-line) / <alpha-value>)",
          text: "rgb(var(--v2-text) / <alpha-value>)",
          text2: "rgb(var(--v2-text2) / <alpha-value>)",
          text3: "rgb(var(--v2-text3) / <alpha-value>)",
          accent: "rgb(var(--v2-accent) / <alpha-value>)",
          green: "rgb(var(--v2-green) / <alpha-value>)",
          orange: "rgb(var(--v2-orange) / <alpha-value>)",
          red: "rgb(var(--v2-red) / <alpha-value>)",
          purple: "rgb(var(--v2-purple) / <alpha-value>)",
          teal: "rgb(var(--v2-teal) / <alpha-value>)",
          onaccent: "rgb(var(--v2-on-accent) / <alpha-value>)",
          gold: "rgb(var(--v2-gold) / <alpha-value>)",
          inkcard: "rgb(var(--v2-ink-card) / <alpha-value>)",
          inkcardtext: "rgb(var(--v2-ink-card-text) / <alpha-value>)",
          inkcardmuted: "rgb(var(--v2-ink-card-muted) / <alpha-value>)",
        },
      },
    },
  },
  plugins: [],
};

export default config;
