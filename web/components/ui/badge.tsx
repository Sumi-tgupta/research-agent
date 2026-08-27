import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
  {
    variants: {
      variant: {
        default:
          "border-transparent bg-primary/15 text-primary-foreground/90 ring-1 ring-inset ring-primary/30",
        secondary:
          "border-transparent bg-secondary text-secondary-foreground",
        outline: "border-border text-foreground",
        // Claim-verdict semantics used across the sources panel & report.
        corroborated:
          "border-transparent bg-primary/15 text-foreground ring-1 ring-inset ring-primary/40",
        single_source:
          "border-transparent bg-accent/15 text-foreground ring-1 ring-inset ring-accent/40",
        contradicted:
          "border-transparent bg-destructive/15 text-foreground ring-1 ring-inset ring-destructive/40",
        unverified:
          "border-transparent bg-muted text-muted-foreground ring-1 ring-inset ring-border",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props} />
  );
}

export { Badge, badgeVariants };
