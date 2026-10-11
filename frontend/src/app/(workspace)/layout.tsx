import type { Metadata } from "next";
import { Shell } from "@/components/workspace/Shell";
import "./workspace.css";

// The signed-in workspace: /dashboard, /runs/<id>, /agents, /memory.
export const metadata: Metadata = {
  title: "EvoLab",
  description: "Supervise EvoLab research runs: approve plans, watch agents work, read the report.",
};

export default function V2Layout({ children }: { children: React.ReactNode }) {
  return <Shell>{children}</Shell>;
}
