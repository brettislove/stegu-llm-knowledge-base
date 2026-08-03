import React, { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

// The backend's free-tier host sleeps after 15 min idle and takes up to
// ~50s to wake on the next request. Below this threshold a load is almost
// certainly fast (server already warm), so we only swap in the wake-up
// explanation once a fetch has actually been hanging long enough to look
// broken rather than just "loading".
const WAKE_HINT_DELAY_MS = 4000;

function useWakeHint() {
  const [showWakeHint, setShowWakeHint] = useState(false);
  useEffect(() => {
    const timer = setTimeout(() => setShowWakeHint(true), WAKE_HINT_DELAY_MS);
    return () => clearTimeout(timer);
  }, []);
  return showWakeHint;
}

/** Single-line variant for tight spaces (dashboard tiles, inline stats). */
export function LoadingNoticeCompact({ className, label = "Načítání…" }) {
  const showWakeHint = useWakeHint();
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-[11.5px] text-muted-foreground", className)}>
      <Loader2 className="h-3 w-3 shrink-0 animate-spin" strokeWidth={2} />
      {showWakeHint ? "Server se probouzí… (~50 s)" : label}
    </span>
  );
}

/** Full variant for panel-level empty/loading states. */
export default function LoadingNotice({ className, label = "Načítání…" }) {
  const showWakeHint = useWakeHint();
  return (
    <div className={cn("flex flex-col gap-2", className)}>
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" strokeWidth={2} />
        {label}
      </div>
      {showWakeHint && (
        <p className="max-w-sm text-[12.5px] leading-relaxed text-muted-foreground">
          Server byl uspán kvůli neaktivitě a teď se probouzí — první načtení může trvat až
          50 sekund. Další požadavky už budou rychlé.
        </p>
      )}
    </div>
  );
}
