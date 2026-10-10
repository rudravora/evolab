import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class", '[data-theme="dark"]'],
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
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
        canvas: {
          DEFAULT: "var(--canvas-void)",
          subtle: "var(--canvas-subtle)",
          elevated: "var(--canvas-elevated)",
        },
        card: {
          DEFAULT: "var(--card-bg)",
          hover: "var(--card-hover)",
          border: "var(--border-subtle)",
        },
        cyan: {
          DEFAULT: "var(--cyan-core)",
          dim: "var(--cyan-dim)",
          glow: "var(--cyan-glow)",
          highlight: "var(--cyan-highlight)",
        },
        amber: {
          DEFAULT: "var(--amber-core)",
          dim: "var(--amber-dim)",
          glow: "var(--amber-glow)",
          highlight: "var(--amber-highlight)",
        },
        foreground: {
          DEFAULT: "var(--text-primary)",
          secondary: "var(--text-secondary)",
          muted: "var(--text-muted)",
          faint: "var(--text-faint)",
        },
        border: {
          subtle: "var(--border-subtle)",
          medium: "var(--border-medium)",
          highlight: "var(--border-highlight)",
        },
      },
      fontFamily: {
        sans: [
          "var(--font-geist-sans)",
          "-apple-system",
          "BlinkMacSystemFont",
          '"Segoe UI"',
          "Roboto",
          '"Helvetica Neue"',
          "Arial",
          "sans-serif",
        ],
        mono: [
          "var(--font-jetbrains-mono)",
          '"SFMono-Regular"',
          "Consolas",
          '"Liberation Mono"',
          "Menlo",
          "Courier",
          "monospace",
        ],
      },
      borderRadius: {
        none: "0px",
        btn: "8px",
        card: "12px",
        panel: "16px",
        full: "9999px",
      },
      boxShadow: {
        "inner-bevel": "inset 0 1px 0 rgba(255, 255, 255, 0.08)",
        "glow-cyan": "0 0 24px -4px rgba(56, 189, 248, 0.28)",
        "glow-amber": "0 0 24px -4px rgba(245, 158, 11, 0.24)",
        "card-depth": "0 8px 32px -8px rgba(0, 0, 0, 0.6)",
      },
      transitionTimingFunction: {
        spring: "cubic-bezier(0.16, 1, 0.3, 1)",
        smooth: "cubic-bezier(0.25, 1, 0.5, 1)",
      },
    },
  },
  plugins: [],
};

export default config;
