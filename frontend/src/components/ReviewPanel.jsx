import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import { parseFeedbackLog, parseLessons } from "@/lib/parseWiki";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import LoadingNotice from "@/components/ui/loading-notice";

// entry.status comes straight from feedback_log.md's own "status: <word>"
// field (English by design — parsed by the backend's distill step too), so
// only the displayed label is translated here, not the underlying value.
const STATUS_LABELS = {
  processed: "zpracováno",
  unprocessed: "nezpracováno",
  unknown: "neznámé",
};

export default function ReviewPanel() {
  const [feedbackLog, setFeedbackLog] = useState("");
  const [lessons, setLessons] = useState("");
  const [lintReport, setLintReport] = useState("");
  const [busy, setBusy] = useState(false);
  const [lintBusy, setLintBusy] = useState(false);
  const [summary, setSummary] = useState(null);
  const [lintSummary, setLintSummary] = useState(null);
  const [error, setError] = useState(null);
  const [view, setView] = useState("parsed"); // "parsed" | "raw"
  const [initialLoading, setInitialLoading] = useState(true);

  async function refresh() {
    try {
      const [fb, ls, lr] = await Promise.all([
        api.getFile("feedback_log.md"),
        api.getFile("lessons.md"),
        api.getFile("lint-report.md"),
      ]);
      setFeedbackLog(fb.content);
      setLessons(ls.content);
      setLintReport(lr.content);
    } catch (e) {
      setError(e.message);
    } finally {
      setInitialLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function runDistill() {
    setBusy(true);
    setSummary(null);
    setError(null);
    try {
      const { summary } = await api.distill();
      setSummary(summary);
      await refresh();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function runLintCheck() {
    setLintBusy(true);
    setLintSummary(null);
    setError(null);
    try {
      const { summary } = await api.lint();
      setLintSummary(summary);
      await refresh();
    } catch (e) {
      setError(e.message);
    } finally {
      setLintBusy(false);
    }
  }

  const entries = parseFeedbackLog(feedbackLog);
  const unprocessedCount = entries.filter((e) => e.status === "unprocessed").length;
  const lessonSections = parseLessons(lessons);

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="border-b border-border px-7 pb-3.5 pt-5">
        <h1 className="font-display text-[22px] font-semibold">Zkontrolovat zpětnou vazbu</h1>
        <p className="mt-1 text-[13px] text-muted-foreground">
          Označené opravy čekají zde, dokud nespustíte destilaci - ta je převede buď na
          přímou opravu stránky, nebo na trvalé pravidlo v lessons.md. Kontrola wiki health
          níže je pouze pro reportování - sama nic neopravuje.
        </p>
      </div>
      <div className="flex-1 overflow-y-auto px-7 py-5">
        <div className="flex flex-wrap items-center gap-3">
          <Button onClick={runDistill} disabled={busy || unprocessedCount === 0}>
            {busy
              ? "Probíhá destilace…"
              : `Spustit destilaci${unprocessedCount ? ` (${unprocessedCount} čeká)` : ""}`}
          </Button>
          <Tabs value={view} onValueChange={setView}>
            <TabsList>
              <TabsTrigger value="parsed">Analyzováno</TabsTrigger>
              <TabsTrigger value="raw">Čistý markdown</TabsTrigger>
            </TabsList>
          </Tabs>
        </div>

        {error && (
          <Card className="mt-4 border-l-[3px] border-l-[hsl(var(--restricted))]">
            <CardContent className="p-3.5 text-sm">Chyba: {error}</CardContent>
          </Card>
        )}
        {summary && (
          <Card className="mt-4 border-l-[3px] border-l-primary">
            <CardContent className="whitespace-pre-wrap p-3.5 text-sm">{summary}</CardContent>
          </Card>
        )}

        {/* --- Feedback --- */}
        <h2 className="mt-6 mb-2 font-display text-base font-semibold">Zpětná vazba</h2>
        {view === "parsed" ? (
          initialLoading ? (
            <LoadingNotice />
          ) : entries.length === 0 ? (
            <p className="text-sm text-muted-foreground">Zatím nebyla zaznamenána žádná zpětná vazba.</p>
          ) : (
            <div className="flex flex-col gap-3">
              {entries.map((entry, i) => (
                <Card key={i}>
                  <CardHeader className="flex-row items-center justify-between space-y-0 pb-2">
                    <span className="font-mono text-[11px] text-muted-foreground">{entry.date}</span>
                    <Badge variant={entry.status === "processed" ? "public" : "internal"}>
                      {STATUS_LABELS[entry.status] || entry.status}
                    </Badge>
                  </CardHeader>
                  <CardContent className="flex flex-col gap-2 pt-0 text-sm">
                    {entry.question && (
                      <div>
                        <span className="font-medium">Otázka: </span>
                        {entry.question}
                      </div>
                    )}
                    {entry.badAnswer && (
                      <div>
                        <span className="font-medium">Označená odpověď: </span>
                        <span className="text-muted-foreground">{entry.badAnswer}</span>
                      </div>
                    )}
                    {entry.correction && (
                      <div>
                        <span className="font-medium">Oprava: </span>
                        {entry.correction}
                      </div>
                    )}
                  </CardContent>
                </Card>
              ))}
            </div>
          )
        ) : (
          <Card>
            <CardContent className="p-4">
              <pre className="whitespace-pre-wrap font-mono text-xs text-muted-foreground">
                {feedbackLog || "(prázdné)"}
              </pre>
            </CardContent>
          </Card>
        )}

        {/* --- Lessons --- */}
        <h2 className="mt-7 mb-2 font-display text-base font-semibold">Trvalá poučení</h2>
        {view === "parsed" ? (
          initialLoading ? (
            <LoadingNotice />
          ) : lessonSections.length === 0 ? (
            <p className="text-sm text-muted-foreground">Zatím nebyla destilována žádná poučení.</p>
          ) : (
            <div className="flex flex-col gap-3">
              {lessonSections.map((section, i) => (
                <Card key={i}>
                  <CardHeader className="pb-2">
                    <CardTitle>{section.title}</CardTitle>
                  </CardHeader>
                  <CardContent className="pt-0">
                    <ul className="list-disc space-y-1 pl-5 text-sm">
                      {section.items.map((item, j) => (
                        <li key={j}>{item}</li>
                      ))}
                    </ul>
                  </CardContent>
                </Card>
              ))}
            </div>
          )
        ) : (
          <Card>
            <CardContent className="p-4">
              <pre className="whitespace-pre-wrap font-mono text-xs text-muted-foreground">
                {lessons || "(prázdné)"}
              </pre>
            </CardContent>
          </Card>
        )}

        {/* --- Wiki health (lint) --- */}
        <div className="mt-8 flex items-center justify-between">
          <h2 className="font-display text-base font-semibold">Stav wiki</h2>
          <Button variant="secondary" size="sm" onClick={runLintCheck} disabled={lintBusy}>
            {lintBusy ? "Kontroluji…" : "Spustit kontrolu wiki"}
          </Button>
        </div>
        <p className="mt-1 text-[13px] text-muted-foreground">
          Kontroluje osiřelé stránky, nefunkční odkazy, zastaralá tvrzení, chybějící
          frontmatter a rozpory. Pouze reportuje — nic se zde automaticky neopravuje.
        </p>
        {lintSummary && (
          <Card className="mt-3 border-l-[3px] border-l-primary">
            <CardContent className="whitespace-pre-wrap p-3.5 text-sm">{lintSummary}</CardContent>
          </Card>
        )}
        <Card className="mt-3">
          <CardContent className="p-4">
            {initialLoading ? (
              <LoadingNotice />
            ) : (
              <pre className="whitespace-pre-wrap font-mono text-xs text-muted-foreground">
                {lintReport || "(prázdné)"}
              </pre>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}