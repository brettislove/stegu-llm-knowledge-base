import React, { useEffect, useState } from "react";
import { Sun, Moon } from "lucide-react";
import { cn } from "@/lib/utils";
import { getInitialTheme, setTheme as persistTheme } from "@/lib/theme.js";

// Fixed top-right, same position/behavior as the mockup: syncs to
// whichever theme is actually applied on load (OS preference or a stored
// choice) rather than defaulting the sun icon "on" regardless of what's
// rendered — that mismatch was a real bug caught and fixed in the mockup.
export default function ThemeToggle() {
  const [theme, setThemeState] = useState(getInitialTheme);

  useEffect(() => {
    persistTheme(theme);
  }, [theme]);

  return (
    <div
      className="fixed right-4 top-6 z-50 flex gap-1 rounded-full border border-border bg-card p-1 shadow-brand"
      role="group"
      aria-label="Motiv"
    >
      <button
        aria-label="Světlý motiv"
        onClick={() => setThemeState("light")}
        className={cn(
          "flex h-7 w-7 items-center justify-center rounded-full text-muted-foreground",
          theme === "light" && "bg-warn-tint text-primary"
        )}
      >
        <Sun className="h-3.5 w-3.5" />
      </button>
      <button
        aria-label="Tmavý motiv"
        onClick={() => setThemeState("dark")}
        className={cn(
          "flex h-7 w-7 items-center justify-center rounded-full text-muted-foreground",
          theme === "dark" && "bg-warn-tint text-primary"
        )}
      >
        <Moon className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}
