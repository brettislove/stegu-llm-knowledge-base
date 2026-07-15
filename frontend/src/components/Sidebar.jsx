import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import { cn } from "@/lib/utils";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";

const CATEGORIES = [
  "products",
  "pricing",
  "installation",
  "chemistry",
  "complaints",
  "logistics",
  "business",
  "general",
  "internal_process",
];

const TABS = [
  { id: "ask", label: "Ask" },
  { id: "ingest", label: "Nahrát" },
  { id: "review", label: "Zkontrolovat zpětnou vazbu" },
];

export default function Sidebar({ tab, setTab, onOpenFile }) {
  const [expanded, setExpanded] = useState(null);
  // Loaded once, eagerly, for ALL categories on mount — fixes counts only
  // appearing after a category is clicked.
  const [filesByCategory, setFilesByCategory] = useState({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    Promise.all(
      CATEGORIES.map(async (cat) => {
        try {
          const { files } = await api.listFiles(cat);
          return [cat, files];
        } catch {
          return [cat, []];
        }
      })
    ).then((entries) => {
      if (cancelled) return;
      setFilesByCategory(Object.fromEntries(entries));
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="flex h-full flex-col overflow-hidden border-r border-border bg-card">
      <div className="border-b border-border px-[18px] py-5">
        <div className="font-display text-xl font-semibold">Stegu KB</div>
        <div className="mt-0.5 font-mono text-[10px] uppercase tracking-wide text-muted-foreground">
          Firemní wiki
        </div>
      </div>

      <div className="px-[18px] pb-1.5 pt-4 font-mono text-[10px] uppercase tracking-wide text-muted-foreground">
        Katalog souborů
      </div>

      <ScrollArea className="flex-1 min-h-0">
        <ul className="flex flex-col gap-0.5 px-2 pb-3">
          {CATEGORIES.map((cat) => {
            const files = filesByCategory[cat] || [];
            const isExpanded = expanded === cat;
            return (
              <li key={cat}>
                <button
                  onClick={() => setExpanded(isExpanded ? null : cat)}
                  className={cn(
                    "flex w-full items-center justify-between rounded-md px-3 py-2 font-mono text-[12.5px] transition-colors",
                    isExpanded ? "bg-primary text-primary-foreground" : "hover:bg-muted"
                  )}
                >
                  <span>{cat}</span>
                  <span className={cn("text-[11px]", isExpanded ? "text-primary-foreground/75" : "text-muted-foreground")}>
                    {loading ? "…" : files.length}
                  </span>
                </button>

                {isExpanded && (
                  // mt-1.5 + ml-3 pl-3 border-l gives clear visual nesting —
                  // fixes the "not enough spacing between category and files" bug
                  <ul className="ml-3 mt-1.5 mb-2 flex flex-col gap-0.5 border-l border-border pl-3">
                    {files.length === 0 && (
                      <li className="py-1 font-mono text-[11px] text-muted-foreground">(empty)</li>
                    )}
                    {files.map((f) => (
                      <li key={f}>
                        <button
                          onClick={() => onOpenFile(f)}
                          className="w-full rounded-sm px-2 py-1 text-left font-mono text-[11.5px] text-muted-foreground hover:bg-muted hover:text-foreground"
                        >
                          {f.split("/").pop()}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            );
          })}
        </ul>
      </ScrollArea>

      <Separator />
      <div className="flex flex-col py-2">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={cn(
              "border-l-[3px] px-[18px] py-3.5 text-left text-[13.5px] font-medium transition-colors",
              tab === t.id
                ? "border-l-primary bg-background text-foreground"
                : "border-l-transparent text-muted-foreground hover:text-foreground"
            )}
          >
            {t.label}
          </button>
        ))}
      </div>
    </div>
  );
}
