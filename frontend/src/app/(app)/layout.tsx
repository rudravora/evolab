import { AppShell } from "@/components/app/AppShell";

// Signed-in area: dashboard, runs, agents, memory.
export default function AppLayout({ children }: { children: React.ReactNode }) {
  return <AppShell>{children}</AppShell>;
}
