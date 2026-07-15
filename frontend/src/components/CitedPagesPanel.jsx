import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import AccessStamp, { parseAccess, parseFrontmatterField } from "./AccessStamp.jsx";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "./ui/badge.jsx";

export default function CitedPagesPanel({ paths }) {
  const [cards, setCards] = useState({});

  useEffect(() => {
    let cancelled = false;
    paths.forEach(async (path) => {
      if (cards[path]) return;
      try {
        const { content } = await api.getFile(path);
        if (cancelled) return;
        setCards((prev) => ({
          ...prev,
          [path]: {
            access: parseAccess(content),
            category: parseFrontmatterField(content, "category"),
            docType: parseFrontmatterField(content, "doc_type"),
            validUntil: parseFrontmatterField(content, "valid_until"),
          },
        }));
      } catch {
        setCards((prev) => ({ ...prev, [path]: { error: true } }));
      }
    });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [paths]);

  return (
    <div className="flex h-full flex-col overflow-hidden border-l border-border bg-card">
      <div className="px-4 pb-3 pt-5 font-mono text-[10px] uppercase tracking-wide text-muted-foreground">
        Odkazované stránky
      </div>
      <ScrollArea className="flex-1 min-h-0 px-4 pb-4">
        {paths.length === 0 && (
          <p className="text-[12.5px] italic text-muted-foreground">
            Soubory, které asistent použil pro odpověď na otázku, se zobrazují s označenou úrovní přístupu.
          </p>
        )}
        <div className="flex flex-col gap-3">
          {paths.map((path) => {
            const card = cards[path];
            if (!card) return null;
            if (card.error) {
              return (
                <Card key={path} className="bg-[hsl(var(--card-index))] animate-fade-in">
                  <CardContent className="p-3">
                    <div className="break-all font-mono text-[11.5px]">{path}</div>
                    <div className="mt-1.5 text-[11px] text-muted-foreground">Nelze načíst tuto stránku.</div>
                  </CardContent>
                </Card>
              );
            }
            return (
              <Card key={path} className="bg-[hsl(var(--card-index))] animate-fade-in">
                {/* flex row keeps the stamp beside the path, never overlapping it */}
                <CardHeader className="flex-row items-start justify-between gap-2 space-y-0 p-3 pb-0">
                  <div className="break-all font-mono text-[11.5px] leading-snug">{path}</div>
                  <Badge variant={card.access}>
                    {card.access}
                  </Badge>
                </CardHeader>
                <CardContent className="p-3 pt-1.5 text-[11px] text-muted-foreground">
                  {card.category && <>category: {card.category}</>}
                  {card.docType && <> · doc_type: {card.docType}</>}
                  {card.validUntil && (
                    <>
                      <br />
                      valid until: {card.validUntil}
                    </>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      </ScrollArea>
    </div>
  );
}
