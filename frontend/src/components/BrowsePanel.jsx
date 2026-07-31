import React, { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api } from "../api.js";
import { parseAccess, parseFrontmatterField } from "./AccessStamp.jsx";
import { Badge, BadgeDot } from "@/components/ui/badge";
import { Folder, FileText, Cloud } from "lucide-react";
import { cn } from "@/lib/utils";

const CATEGORIES = [
  "system",
  "firma",
  "produkty",
  "ceniky-a-kalkulace",
  "certifikace",
  "montaz-a-navody",
  "logistika",
  "marketing",
  "data-a-analyzy",
  "nastroje",
  "pravo-a-admin",
];

const ACCESS_BADGE = {
  public: { variant: "success", label: "veřejné" },
  internal: { variant: "internal", label: "interní" },
  restricted: { variant: "restricted", label: "omezené" },
};

function stripFrontmatter(content) {
  return content.replace(/^---\n[\s\S]*?\n---\n?/, "").trim();
}

export default function BrowsePanel({ initialPath }) {
  const [filesByCategory, setFilesByCategory] = useState({});
  const [loadingTree, setLoadingTree] = useState(true);
  const [expandedCategory, setExpandedCategory] = useState("produkty");
  const [currentPath, setCurrentPath] = useState(null);
  const [page, setPage] = useState(null);

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
      setLoadingTree(false);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!initialPath) return;
    const cat = initialPath.split("/")[0];
    if (CATEGORIES.includes(cat)) setExpandedCategory(cat);
    openFile(initialPath);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialPath]);

  async function openFile(path) {
    setCurrentPath(path);
    setPage(null);
    try {
      const { content, folderWebUrl } = await api.getFile(path);
      setPage({
        title: parseFrontmatterField(content, "title") || path.split("/").pop(),
        access: parseAccess(content),
        category: parseFrontmatterField(content, "category"),
        docType: parseFrontmatterField(content, "doc_type"),
        updated: parseFrontmatterField(content, "last_updated"),
        body: stripFrontmatter(content),
        folderWebUrl,
      });
    } catch (e) {
      setPage({ error: e.message });
    }
  }

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="border-b border-border bg-card px-10 py-6 pr-24 mobile:pl-16">
        <h2 className="font-display text-[26px] font-bold text-foreground">Prohlížet</h2>
      </div>

      <div className="min-h-0 flex-1 overflow-hidden p-6 mobile:p-4">
        <div className="mx-auto flex h-full max-w-[1040px] overflow-hidden rounded-lg border border-border bg-card shadow-brand mobile:flex-col">
          <div className="w-[230px] shrink-0 overflow-y-auto border-r border-border bg-muted p-3 mobile:max-h-[240px] mobile:w-full mobile:border-b mobile:border-r-0">
            {CATEGORIES.map((cat) => {
              const files = filesByCategory[cat] || [];
              const isExpanded = expandedCategory === cat;
              return (
                <div key={cat}>
                  <button
                    onClick={() => setExpandedCategory(isExpanded ? null : cat)}
                    className={cn(
                      "flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-[13px] font-medium text-muted-foreground transition-colors hover:bg-card",
                      isExpanded && "bg-warn-tint font-semibold text-primary hover:bg-warn-tint"
                    )}
                  >
                    <Folder className="h-3.5 w-3.5 shrink-0" strokeWidth={1.6} />
                    <span className="truncate">{cat}</span>
                    <span className="ml-auto shrink-0 text-[10.5px] tabular-nums">
                      {loadingTree ? "…" : files.length}
                    </span>
                  </button>
                  {isExpanded && (
                    <ul className="mb-2 ml-3 mt-1 flex flex-col gap-0.5 border-l border-border pl-3">
                      {files.length === 0 && (
                        <li className="py-1 text-[11px] text-muted-foreground">(prázdné)</li>
                      )}
                      {files.map((f) => (
                        <li key={f}>
                          <button
                            onClick={() => openFile(f)}
                            className={cn(
                              "w-full truncate rounded-sm px-2 py-1 text-left font-mono text-[11.5px] text-muted-foreground hover:bg-card hover:text-foreground",
                              currentPath === f && "bg-card font-semibold text-primary"
                            )}
                          >
                            {f.split("/").pop()}
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              );
            })}
          </div>

          <div className="min-w-0 flex-1 overflow-y-auto p-7">
            {!currentPath && (
              <p className="text-sm italic text-muted-foreground">
                Vyberte soubor vlevo, nebo klikněte na odkazovaný soubor v odpovědi na dotaz.
              </p>
            )}
            {currentPath && !page && <p className="text-sm text-muted-foreground">Načítání…</p>}
            {page?.error && (
              <p className="text-sm text-[hsl(var(--restricted))]">Chyba: {page.error}</p>
            )}
            {page && !page.error && (
              <>
                <div className="mb-1.5 flex items-start justify-between gap-3">
                  <h3 className="font-display text-[21px] font-bold text-foreground">{page.title}</h3>
                  <div className="flex shrink-0 items-center gap-2">
                    {page.folderWebUrl && (
                      <a
                        href={page.folderWebUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        title="Zobrazit složku na OneDrive"
                        className="flex h-6 w-6 items-center justify-center rounded-md text-[hsl(var(--info))] transition-colors hover:bg-warn-tint"
                      >
                        <Cloud className="h-4 w-4" strokeWidth={1.8} />
                      </a>
                    )}
                    {page.access && page.access !== "unknown" && (
                      <Badge variant={ACCESS_BADGE[page.access]?.variant || "outline"}>
                        <BadgeDot />
                        {ACCESS_BADGE[page.access]?.label || page.access}
                      </Badge>
                    )}
                  </div>
                </div>
                <div className="mb-4 flex flex-wrap gap-4 text-[11.5px] text-muted-foreground">
                  {page.category && (
                    <span>
                      Kategorie: <b className="font-semibold text-foreground">{page.category}</b>
                    </span>
                  )}
                  {page.docType && (
                    <span>
                      Typ: <b className="font-semibold text-foreground">{page.docType}</b>
                    </span>
                  )}
                  {page.updated && (
                    <span>
                      Aktualizováno: <b className="font-semibold text-foreground">{page.updated}</b>
                    </span>
                  )}
                </div>
                <div className="prose prose-sm dark:prose-invert max-w-none text-[14px] leading-relaxed text-muted-foreground">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{page.body}</ReactMarkdown>
                </div>
                <div className="mt-5 flex items-center gap-2 border-t border-border pt-4 text-[12.5px] text-muted-foreground">
                  <FileText className="h-3.5 w-3.5 shrink-0" strokeWidth={1.5} />
                  Zdrojový soubor: <span className="font-mono">{currentPath}</span>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
