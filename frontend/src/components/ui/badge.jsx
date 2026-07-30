import React from "react";
import { cva } from "class-variance-authority";
import { cn } from "@/lib/utils";

// Pill shape with a small colored dot, tinted background + colored text +
// colored border — one variant per state, matching the mockup's
// `.badge-*` classes exactly. public/internal/restricted (the wiki's
// access levels) reuse the same success/gold/warn hues rather than a
// separate color family, since that semantic mapping already fit
// (public=safe, internal=caution, restricted=stop).
const badgeVariants = cva(
  "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11.5px] font-medium leading-none whitespace-nowrap transition-colors",
  {
    variants: {
      variant: {
        default: "border-transparent bg-primary text-primary-foreground",
        secondary: "border-transparent bg-muted text-muted-foreground",
        outline: "text-muted-foreground border-border bg-card",
        success: "border-success-tint-border bg-success-tint text-success",
        warn: "border-warn-tint-border bg-warn-tint text-primary",
        info: "border-transparent bg-info-tint text-info",
        gold: "border-gold-tint-border bg-gold-tint text-gold-dark",
        public: "border-transparent bg-success-tint text-success",
        internal: "border-transparent bg-gold-tint text-gold-dark",
        restricted: "border-transparent bg-warn-tint text-primary",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
);

function Badge({ className, variant, ...props }) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}

/** Small colored dot for the mockup's dot-prefixed badges — prepend as
 * `<Badge variant="success"><BadgeDot />Skladem Praha</Badge>`. */
function BadgeDot({ className }) {
  return <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full bg-current", className)} />;
}

export { Badge, BadgeDot, badgeVariants };
