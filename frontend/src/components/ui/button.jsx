import React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        // Primary — solid brand red. The dominant action everywhere.
        default: "bg-primary text-primary-foreground hover:bg-[hsl(var(--primary-hover))]",
        // Outline — red border on white/card, matches the mockup's
        // secondary CTA (e.g. "Zobrazit varianty").
        outline: "bg-card text-primary border border-primary hover:bg-warn-tint",
        // Dark — solid ink, for de-emphasized-but-firm actions (e.g. a
        // future "Stáhnout katalog").
        dark: "bg-foreground text-background hover:opacity-90",
        // Muted — quiet/secondary actions that shouldn't compete for
        // attention (e.g. "Zpět na výběr").
        muted: "bg-muted text-muted-foreground border border-border hover:bg-accent",
        // Success — approve-style actions (Schválit).
        success: "bg-success text-success-foreground hover:opacity-90",
        secondary: "bg-card text-foreground border border-border hover:bg-muted",
        ghost: "hover:bg-muted text-foreground",
        link: "text-muted-foreground underline-offset-4 hover:underline",
        destructive: "bg-[hsl(var(--restricted))] text-white hover:opacity-90",
      },
      size: {
        default: "h-9 px-4 py-2",
        sm: "h-8 rounded-md px-3 text-xs",
        lg: "h-10 rounded-md px-6",
        icon: "h-9 w-9",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
);

const Button = React.forwardRef(({ className, variant, size, asChild = false, ...props }, ref) => {
  const Comp = asChild ? Slot : "button";
  return <Comp className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />;
});
Button.displayName = "Button";

export { Button, buttonVariants };
