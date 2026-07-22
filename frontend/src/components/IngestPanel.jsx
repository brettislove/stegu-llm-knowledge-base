import React, { useRef, useState } from "react";
import { api, pdfToBase64 } from "../api.js";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

// Expanded file coverage matrix
const ACCEPTED_EXTENSIONS = [".pdf", ".md", ".markdown", ".txt", ".docx", ".xlsx", ".csv"];

function isAccepted(file) {
  return ACCEPTED_EXTENSIONS.some((ext) => file.name.toLowerCase().endsWith(ext));
}

export default function IngestPanel() {
  const [file, setFile] = useState(null);
  const [dragOver, setDragOver] = useState(false);
  const [busy, setBusy] = useState(false);
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState(null);
  const inputRef = useRef(null);

  function pickFile(f) {
    if (f && isAccepted(f)) {
      setFile(f);
      setSummary(null);
      setError(null);
    }
  }

  async function runIngest() {
    if (!file) return;
    setBusy(true);
    setSummary(null);
    setError(null);
    try {
      // Every file type now goes through unified base64 formatting
      const base64Data = await pdfToBase64(file);
      const { summary } = await api.ingest(file.name, base64Data);
      setSummary(summary);
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
          Vložte zdrojový soubor (.pdf, .md, .markdown, .txt, .docx, .xlsx, .csv).
          Struktury dokumentu a tabulkový obsah jsou pro agenta analyzovány automaticky.
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
          Vložte dokument nebo datový soubor sem, nebo klikněte pro výběr
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
          {busy ? "Zpracovávám…" : "Spustit zpracování"}
        </Button>

        {error && (
          <Card className="mt-5 border-l-[3px] border-l-[hsl(var(--restricted))]">
            <CardContent className="p-3.5 text-sm">Chyba: {error}</CardContent>
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