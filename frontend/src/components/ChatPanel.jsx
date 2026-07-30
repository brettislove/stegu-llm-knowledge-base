import React, { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api } from "../api.js";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { FileText, Flag, CheckCircle2, ThumbsUp, ThumbsDown, Send } from "lucide-react";
import { cn } from "@/lib/utils";

const CITE_REGEX = /\b(?:[a-z0-9_-]+\/)?[a-z0-9-]+\.md\b/gi;

function extractCitedPaths(text) {
  const found = text.match(CITE_REGEX) || [];
  return [...new Set(found)];
}

// How many prior turns to resend as context for in-session follow-up
// memory — enough for "what about the other one" style follow-ups
// without letting the request grow unbounded over a long session.
const HISTORY_TURNS = 8;

export default function ChatPanel({ onOpenInBrowse }) {
  const [mode, setMode] = useState("internal");
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState([]);
  const [pending, setPending] = useState(false);
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, pending]);

  async function send() {
    const question = input.trim();
    if (!question || pending) return;
    setInput("");

    const history = messages
      .filter((m) => !m.text?.startsWith("Error:"))
      .slice(-HISTORY_TURNS)
      .map((m) => ({ role: m.role === "user" ? "user" : "assistant", content: m.text }));

    setMessages((prev) => [...prev, { id: crypto.randomUUID(), role: "user", text: question }]);
    setPending(true);
    try {
      const res = await api.query(question, mode, history);
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "agent",
          text: res.answer,
          question,
          feedbackOpen: false,
          totalTokens: res.total_tokens,
          cachePct: res.cache_pct,
          costCzk: res.cost_czk,
        },
      ]);
    } catch (e) {
      setMessages((prev) => [
        ...prev,
        { id: crypto.randomUUID(), role: "agent", text: `Error: ${e.message}` },
      ]);
    } finally {
      setPending(false);
    }
  }

  function toggleFeedback(id) {
    setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, feedbackOpen: !m.feedbackOpen } : m)));
  }

  async function submitFeedback(msg, correction) {
    if (!correction.trim()) return;
    await api.feedback(msg.question, msg.text, correction.trim());
    setMessages((prev) =>
      prev.map((m) => (m.id === msg.id ? { ...m, feedbackOpen: false, feedbackSent: true } : m))
    );
  }

  return (
    <div className="flex h-full flex-col bg-background">
      <div className="flex items-center justify-between gap-4 border-b border-border bg-card px-10 py-6 pr-24 mobile:pl-16">
        <h2 className="font-display text-[26px] font-bold text-foreground">Chat</h2>
        <Tabs value={mode} onValueChange={setMode}>
          <TabsList>
            <TabsTrigger value="internal">Interní</TabsTrigger>
            <TabsTrigger value="public">Pro zákazníka</TabsTrigger>
          </TabsList>
        </Tabs>
      </div>

      <ScrollArea className="min-h-0 flex-1">
        <div className="mx-auto flex max-w-[1040px] flex-col gap-[18px] px-10 py-8">
          {messages.map((m) =>
            m.role === "user" ? (
              <div key={m.id} className="flex animate-fade-in justify-end">
                <div className="max-w-[78%] rounded-xl rounded-br-sm bg-primary px-4 py-3.5 text-[14.5px] leading-relaxed text-primary-foreground">
                  {m.text}
                </div>
              </div>
            ) : (
              <div key={m.id} className="flex animate-fade-in flex-col items-start gap-2">
                <div className="max-w-[78%] rounded-xl rounded-bl-sm border border-border bg-card px-4 py-3.5 text-[14.5px] leading-relaxed text-card-foreground shadow-brand">
                  {!m.text.startsWith("Error:") ? (
                    <div className="prose prose-sm dark:prose-invert max-w-none break-words">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.text}</ReactMarkdown>
                    </div>
                  ) : (
                    <div className="whitespace-pre-wrap text-[hsl(var(--restricted))]">{m.text}</div>
                  )}
                </div>

                {!m.text.startsWith("Error:") && (
                  <>
                    {extractCitedPaths(m.text).length > 0 && (
                      <div className="flex flex-wrap gap-1.5">
                        {extractCitedPaths(m.text).map((path) => (
                          <button
                            key={path}
                            onClick={() => onOpenInBrowse(path)}
                            className="inline-flex items-center gap-1.5 rounded-md border border-border bg-muted px-2.5 py-1 font-mono text-[11.5px] text-muted-foreground transition-colors hover:border-[hsl(var(--warn-tint-border))] hover:bg-warn-tint hover:text-primary"
                          >
                            <FileText className="h-[11px] w-[11px]" strokeWidth={1.6} />
                            {path}
                          </button>
                        ))}
                      </div>
                    )}

                    <div className="flex items-center gap-3 pl-0.5">
                      <div className="flex gap-1">
                        <button
                          aria-label="Užitečná odpověď"
                          className="rounded-md p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-primary"
                        >
                          <ThumbsUp className="h-3.5 w-3.5" strokeWidth={1.7} />
                        </button>
                        <button
                          aria-label="Nepřesná odpověď"
                          onClick={() => toggleFeedback(m.id)}
                          className="rounded-md p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-primary"
                        >
                          <ThumbsDown className="h-3.5 w-3.5" strokeWidth={1.7} />
                        </button>
                      </div>
                      {typeof m.cachePct === "number" && (
                        <span className="text-[11.5px] tabular-nums text-muted-foreground">
                          ~{m.totalTokens?.toLocaleString("cs-CZ")} tokenů (
                          <b className="font-bold text-gold-dark">{m.cachePct}&nbsp;%</b> z cache) · odhad{" "}
                          <b className="font-bold text-gold-dark">{m.costCzk} Kč</b>
                        </span>
                      )}
                    </div>

                    {m.feedbackSent ? (
                      <span className="inline-flex items-center gap-1.5 font-mono text-[11px] font-medium text-success">
                        <CheckCircle2 className="h-3.5 w-3.5" />
                        Zpětná vazba odeslána
                      </span>
                    ) : (
                      m.feedbackOpen && <FeedbackForm onSubmit={(c) => submitFeedback(m, c)} />
                    )}
                  </>
                )}
              </div>
            )
          )}

          {pending && (
            <div className="flex animate-fade-in justify-start">
              <div className="rounded-xl rounded-bl-sm border border-border bg-card px-4 py-3.5 shadow-brand">
                <div className="flex gap-1">
                  <span className="h-2 w-2 animate-bounce rounded-full bg-muted-foreground [animation-delay:-0.3s]" />
                  <span className="h-2 w-2 animate-bounce rounded-full bg-muted-foreground [animation-delay:-0.15s]" />
                  <span className="h-2 w-2 animate-bounce rounded-full bg-muted-foreground" />
                </div>
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>
      </ScrollArea>

      <div className="flex justify-center border-t border-border bg-card">
        <div className="w-full max-w-[1040px] px-10 py-5">
          <div className="flex items-end gap-2.5 rounded-xl border border-border bg-background px-4 py-2.5 shadow-brand focus-within:ring-1 focus-within:ring-ring">
            <Textarea
              placeholder="Zeptejte se na produkt, montáž nebo dostupnost…"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send();
                }
              }}
              className="min-h-[24px] w-full resize-none border-0 bg-transparent p-0 text-[16px] leading-relaxed focus-visible:ring-0"
              rows={1}
            />
            <Button onClick={send} disabled={pending || !input.trim()} size="sm" className="shrink-0 gap-1.5">
              <Send className="h-3.5 w-3.5" />
              Odeslat
            </Button>
          </div>
          <p className="mt-2 text-center text-[11px] text-muted-foreground">
            AI agenti mohou dělat chyby. Před odesláním klientům si informace vždy ověřte.
          </p>
        </div>
      </div>
    </div>
  );
}

function FeedbackForm({ onSubmit }) {
  const [value, setValue] = useState("");
  return (
    <div className="mt-1 flex w-full max-w-[78%] flex-col gap-2 rounded-lg border border-border bg-muted p-3">
      <Input
        placeholder="Co mělo být správně?"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        className="h-8 bg-background text-xs"
      />
      <div className="flex justify-end">
        <Button variant="secondary" size="sm" className="h-7 text-xs" onClick={() => onSubmit(value)}>
          Odeslat opravu
        </Button>
      </div>
    </div>
  );
}
