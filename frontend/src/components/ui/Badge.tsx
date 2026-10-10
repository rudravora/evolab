import * as React from "react";
import { cn } from "@/lib/utils";

export interface BadgeProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: "cyan" | "amber" | "neutral" | "outline";
  dot?: boolean;
}

export const Badge: React.FC<BadgeProps> = ({
  className,
  variant = "cyan",
  dot = false,
  children,
  ...props
}) => {
  const variantStyles = {
    cyan: "bg-cyan/10 text-cyan-highlight border-cyan/25",
    amber: "bg-amber/10 text-amber-highlight border-amber/25",
    neutral: "bg-white/[0.04] text-foreground-secondary border-border-subtle",
    outline: "bg-transparent text-foreground-secondary border-border-medium",
  };

  const dotStyles = {
    cyan: "bg-cyan shadow-[0_0_8px_rgba(56,189,248,0.8)]",
    amber: "bg-amber shadow-[0_0_8px_rgba(245,158,11,0.8)]",
    neutral: "bg-zinc-400",
    outline: "bg-zinc-400",
  };

  return (
    <div
      className={cn(
        "inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-mono tracking-wider border",
        variantStyles[variant],
        className
      )}
      {...props}
    >
      {dot && (
        <span
          className={cn("w-1.5 h-1.5 rounded-full animate-pulse", dotStyles[variant])}
          aria-hidden="true"
        />
      )}
      <span>{children}</span>
    </div>
  );
};
