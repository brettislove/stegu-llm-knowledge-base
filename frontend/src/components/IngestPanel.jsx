import React, { useRef, useState } from "react";
import { pdfToBase64 } from "../api.js";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

// Expanded file coverage matrix
const ACCEPTED_EXTENSIONS = [".pdf", ".md", ".markdown", ".txt", ".docx", ".xlsx", ".csv"];

// Align this with wherever your api.js points requests — this matches the
// default `uvicorn backend.main:app --port 8000` from main.py's docstring.
const apiUrl = import.meta.env.VITE_API_URL || "http://localhost:8000";

// Fixed stage order + Czech labels shown while pending/active — actual
// labels from the backend (event.label) override these once a stage starts.
const STEP_ORDER = [
  { key: "upload", label: "Nahrávání souboru" },
  { key: "hash_check", label: "Kontrola duplicity" },
  { key: "convert", label: "Převod dokumentu" },
  { key: "classify", label: "Klasifikace dokumentu" },
  { key: "write", label: "Zápis do wiki" },
  { key: "finalize", label: "Dokončování" },
];

function initialSteps() {
  return STEP_ORDER.map((s) => ({ ...s, status: "pending", detail: null }));
}

function isAccepted(file) {
  return ACCEPTED_EXTENSIONS.some((ext) => file.name.toLowerCase().endsWith(ext));
}

function StepIcon({ status }) {
  if (status === "done") return <span className="text-primary">●</span>;
  if (status === "active") return <span className="animate-pulse text-primary">◐</span>;
  if (status === "error") return <span className="text-[hsl(var(--restricted))]">✕</span>;
  if (status === "skipped") return <span className="text-muted-foreground">–</span>;
  return <span className="text-muted-foreground">○</span>;
}

function IngestStepper({ steps }) {
  return (
    <div className="mt-5 flex flex-col gap-2">
      {steps.map((step) => (
        <div
          key={step.key}
          className={cn(
            "flex items-center gap-2.5 text-sm",
            step.status === "pending" && "text-muted-foreground",
            step.status === "error" && "text-[hsl(var(--restricted))]"
          )}
        >
          <StepIcon status={step.status} />
          <span className={step.status === "active" ? "font-medium" : ""}>{step.label}</span>
          {step.detail && (
            <span className="ml-1 text-xs text-muted-foreground">
              {step.detail.category}
              {step.detail.topic ? ` / ${step.detail.topic}` : ""} — jistota: {step.detail.confidence}
            </span>
          )}
        </div>
      ))}
    </div>
  );
}

export default function IngestPanel() {
  const [file, setFile] = useState(null);
  const [dragOver, setDragOver] = useState(false);
  const [busy, setBusy] = useState(false);
  const [steps, setSteps] = useState(initialSteps());
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState(null);
  const inputRef = useRef(null);

  function pickFile(f) {
    if (f && isAccepted(f)) {
      setFile(f);
      setSummary(null);
      setError(null);
      setSteps(initialSteps());
    }
  }

  function applyEvent(event) {
    if (event.stage === "finished") {
      setSteps((prev) => prev.map((s) => (s.status === "pending" ? { ...s, status: "skipped" } : s)));
      const result = event.result;
      if (result.status === "ingested") {
        setSummary(result.summary + (result.split_hint ? `\n\n⚠ ${result.split_hint}` : ""));
      } else if (result.status === "unchanged") {
        setSummary(result.message);
      } else if (result.status === "pending_review") {
        setSummary(
          `${result.message}\n\nNavržená klasifikace: ${result.proposed.category}` +
            (result.proposed.topic ? ` / ${result.proposed.topic}` : "") +
            `\nOdůvodnění: ${result.reasoning}`
        );
      }
      return;
    }
    setSteps((prev) =>
      prev.map((s) => {
        if (s.key !== event.stage) return s;
        if (event.status === "start") return { ...s, status: "active", label: event.label || s.label };
        if (event.status === "done") return { ...s, status: "done", detail: event.detail || s.detail };
        if (event.status === "error") return { ...s, status: "error" };
        return s;
      })
    );
    if (event.status === "error") {
      setError(event.message);
    }
  }

  async function runIngest() {
    if (!file) return;
    setBusy(true);
    setSummary(null);
    setError(null);
    setSteps(initialSteps());
    try {
      const base64Data = await pdfToBase64(file);
      // This streams the raw response body, so it can't go through api.js's
      // request() helper — but it still needs the same Clerk auth header
      // that helper attaches, or the backend's auth middleware 401s it.
      const token = await window.Clerk?.session?.getToken();
      const response = await fetch(`${apiUrl}/ingest/stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ filename: file.name, file_base64: base64Data }),
      });
      if (response.status === 401) {
        throw new Error("Přihlášení vypršelo. Obnovte stránku a zkuste to znovu.");
      }
      if (!response.body) {
        throw new Error("Prohlížeč nepodporuje streamování odpovědi.");
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const chunks = buffer.split("\n\n");
        buffer = chunks.pop(); // last (possibly incomplete) chunk stays buffered
        for (const chunk of chunks) {
          const line = chunk.trim();
          if (!line.startsWith("data: ")) continue;
          applyEvent(JSON.parse(line.slice(6)));
        }
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="border-b border-border px-7 pb-3.5 pt-5">
        <h1 className="font-display text-[22px] font-semibold">Přidat dokument</h1>
        <p className="mt-1 text-[13px] text-muted-foreground">
          Vložte zdrojové soubory (.pdf, .md, .markdown, .txt, .docx, .xlsx, .csv). Systém je zpracuje a uloží do wiki.
        </p>
      </div>
      <div className="flex-1 overflow-y-auto px-7 py-5">
        <div
          className={cn(
            "cursor-pointer rounded-md border-2 border-dashed border-border p-10 text-center text-muted-foreground transition-colors",
            dragOver && "border-primary bg-card"
          )}
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragOver(false);
            pickFile(e.dataTransfer.files[0]);
          }}
          onClick={() => inputRef.current?.click()}
        >
          Přetáhněte soubor nebo klikněte pro výběr (povolené typy: {ACCEPTED_EXTENSIONS.join(", ")})
          <input
            ref={inputRef}
            type="file"
            accept={ACCEPTED_EXTENSIONS.join(",")}
            className="hidden"
            onChange={(e) => pickFile(e.target.files[0])}
          />
          {file && (
            <div className="mx-auto mt-3 inline-flex items-center gap-2 rounded-md border border-border bg-card px-2.5 py-1.5 font-mono text-[12.5px]">
              📄 {file.name}
            </div>
          )}
        </div>

        <Button className="mt-4" onClick={runIngest} disabled={!file || busy}>
          {busy ? "Probíhá zpracování…" : "Spustit zpracování"}
        </Button>

        {(busy || steps.some((s) => s.status !== "pending")) && (
          <Card className="mt-5">
            <CardContent className="p-4">
              <IngestStepper steps={steps} />
            </CardContent>
          </Card>
        )}

        {error && (
          <Card className="mt-5 border-l-[3px] border-l-[hsl(var(--restricted))]">
            <CardContent className="p-3.5 text-sm">Error: {error}</CardContent>
          </Card>
        )}
        {summary && (
          <Card className="mt-5 border-l-[3px] border-l-primary">
            <CardContent className="whitespace-pre-wrap p-3.5 text-sm">{summary}</CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
