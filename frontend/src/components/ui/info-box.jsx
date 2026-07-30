import React from "react";
import { cn } from "@/lib/utils";

// Distinct from Card: a 3px colored left border + tinted background, not a
// bordered white card. Matches the mockup's .info-box pattern — used for
// ingest results, pending-review reasoning context, and the Náklady "why
// it's cheap" note.
const VARIANT_CLASSES = {
  tip: "bg-gold-tint border-l-gold",
  warn: "bg-warn-tint border-l-primary",
  ok: "bg-success-tint border-l-success",
};
const LABEL_CLASSES = {
  tip: "text-gold-dark",
  warn: "text-primary",
  ok: "text-success",
};

export function InfoBox({ variant = "tip", label, children, className }) {
  return (
    <div
      className={cn(
        "flex flex-col gap-1 rounded-md border-l-[3px] px-4 py-3.5",
        VARIANT_CLASSES[variant],
        className
      )}
    >
      {label && (
        <span className={cn("text-[11px] font-bold uppercase tracking-wide", LABEL_CLASSES[variant])}>
          {label}
        </span>
      )}
      <div className="text-[13.5px] leading-relaxed text-muted-foreground">{children}</div>
    </div>
  );
}
