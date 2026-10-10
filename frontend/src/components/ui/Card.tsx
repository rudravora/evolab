import * as React from "react";
import { cn } from "@/lib/utils";

export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  hoverable?: boolean;
  glow?: "none" | "cyan" | "amber";
}

export const Card = React.forwardRef<HTMLDivElement, CardProps>(
  ({ className, hoverable = false, glow = "none", children, ...props }, ref) => {
    const glowStyles = {
      none: "",
      cyan: "border-cyan/30 shadow-glow-cyan",
      amber: "border-amber/30 shadow-glow-amber",
    };

    return (
      <div
        ref={ref}
        className={cn(
          "rounded-card bg-card/85 backdrop-blur-md border border-border-subtle p-6 shadow-inner-bevel relative overflow-hidden",
          hoverable &&
            "transition-all duration-200 ease-spring hover:border-border-medium hover:bg-card-hover hover:-translate-y-0.5",
          glowStyles[glow],
          className
        )}
        {...props}
      >
        {children}
      </div>
    );
  }
);

Card.displayName = "Card";
