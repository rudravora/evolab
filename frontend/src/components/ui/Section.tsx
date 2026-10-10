import * as React from "react";
import { cn } from "@/lib/utils";

export interface SectionProps extends React.HTMLAttributes<HTMLElement> {
  spacing?: "tight" | "normal" | "spacious";
  pattern?: boolean;
}

export const Section = React.forwardRef<HTMLElement, SectionProps>(
  ({ className, spacing = "normal", pattern = false, children, ...props }, ref) => {
    const spacingStyles = {
      tight: "py-12 md:py-16",
      normal: "py-20 md:py-28",
      spacious: "py-28 md:py-36",
    };

    return (
      <section
        ref={ref}
        className={cn(
          "relative w-full overflow-hidden",
          spacingStyles[spacing],
          pattern && "bg-grid-pattern",
          className
        )}
        {...props}
      >
        {children}
      </section>
    );
  }
);

Section.displayName = "Section";
