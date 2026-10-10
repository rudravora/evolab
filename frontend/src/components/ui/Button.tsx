import * as React from "react";
import { cn } from "@/lib/utils";

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "outline" | "ghost" | "cyan";
  size?: "sm" | "md" | "lg";
  asChild?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "primary", size = "md", asChild, ...props }, ref) => {
    const baseStyles =
      "inline-flex items-center justify-center font-medium transition-all duration-150 select-none whitespace-nowrap active:scale-[0.98] disabled:pointer-events-none disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan/50";

    const variantStyles = {
      primary:
        "bg-foreground text-canvas hover:bg-zinc-200 shadow-sm border border-transparent",
      cyan:
        "bg-cyan text-canvas font-semibold hover:bg-cyan-highlight shadow-glow-cyan border border-cyan-highlight/30",
      secondary:
        "bg-canvas-elevated text-foreground border border-border-subtle hover:border-cyan/40 hover:bg-card-hover hover:text-foreground",
      outline:
        "bg-transparent text-foreground border border-border-medium hover:border-foreground/30 hover:bg-white/[0.04]",
      ghost:
        "bg-transparent text-foreground-secondary hover:text-foreground hover:bg-white/[0.05]",
    };

    const sizeStyles = {
      sm: "h-8 px-3 text-xs rounded-btn gap-1.5",
      md: "h-10 px-4 text-sm rounded-btn gap-2",
      lg: "h-12 px-6 text-base rounded-btn gap-2.5",
    };

    return (
      <button
        ref={ref}
        className={cn(baseStyles, variantStyles[variant], sizeStyles[size], className)}
        {...props}
      />
    );
  }
);

Button.displayName = "Button";
