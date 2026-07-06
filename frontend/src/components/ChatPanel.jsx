import React, { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Flag, CheckCircle2 } from "lucide-react";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

const CITE_REGEX = /\b(?:[a-z0-9_]+\/)?[a-z0-9-]+\.md\b/gi;

function extractCitedPaths(text) {
  const found = text.match(CITE_REGEX) || [];
  return [...new Set(found)];
}

export default function ChatPanel({ onCitedPaths }) {
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
    setMessages((prev) => [...prev, { id: crypto.randomUUID(), role: "user", text: question }]);
    setPending(true);
    try {
      const { answer } = await api.query(question, mode);
      onCitedPaths(extractCitedPaths(answer));
      setMessages((prev) => [
        ...prev,
        { id: crypto.randomUUID(), role: "agent", text: answer, question, feedbackOpen: false },
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
    // h-full + overflow-hidden on this flex column is what keeps the chat
    // scrolling internally instead of growing the whole page.
    <div className="flex h-full flex-col overflow-hidden">
      <div className="border-b border-border px-7 pb-3.5 pt-5">
        <h1 className="font-display text-[22px] font-semibold">Ask</h1>
        <p className="mt-1 text-[13px] text-muted-foreground">
          Query the wiki directly, or draft an answer for a customer email — access
          filtering changes depending which you pick.
        </p>
      </div>

      <div className="flex min-h-0 flex-1 flex-col gap-3 px-7 py-4">
        <Tabs value={mode} onValueChange={setMode}>
          <TabsList>
            <TabsTrigger value="internal">internal</TabsTrigger>
            <TabsTrigger value="public">public</TabsTrigger>
          </TabsList>
        </Tabs>

        <ScrollArea className="min-h-0 flex-1 rounded-md border border-border bg-background/40 p-4">
          <div className="flex flex-col gap-4">
            {messages.map((m) =>
              m.role === "user" ? (
                <div
                  key={m.id}
                  className="max-w-[640px] animate-fade-in self-end rounded-md bg-primary px-3.5 py-2.5 text-primary-foreground"
                >
                  {m.text}
                </div>
              ) : (
                <div
                  key={m.id}
                  className="max-w-[640px] animate-fade-in whitespace-pre-wrap rounded-md border border-border bg-card px-4 py-3"
                >
                  {m.text}
                  <div className="mt-2.5 flex items-center justify-between border-t border-border pt-2.5">
                    {m.feedbackSent ? (
                      <span className="inline-flex items-center gap-1.5 font-mono text-[11px] font-medium text-[hsl(var(--public))]">
                        <CheckCircle2 className="h-3.5 w-3.5" />
                        feedback recorded
                      </span>
                    ) : (
                      <button
                        className="inline-flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1 font-mono text-[11px] font-medium text-muted-foreground transition-colors hover:border-[hsl(var(--restricted))] hover:text-[hsl(var(--restricted))]"
                        onClick={() => toggleFeedback(m.id)}
                      >
                        <Flag className="h-3.5 w-3.5" />
                        not quite right?
                      </button>
                    )}
                  </div>
                  {m.feedbackOpen && <FeedbackForm onSubmit={(c) => submitFeedback(m, c)} />}
                </div>
              )
            )}
            {pending && (
              <div className="max-w-[640px] rounded-md border border-border bg-card px-4 py-3 italic text-muted-foreground">
                thinking…
              </div>
            )}
            <div ref={bottomRef} />
          </div>
        </ScrollArea>

        <div className="flex gap-2.5">
          <Textarea
            placeholder="Ask a question about the knowledge base…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
            className="flex-1 resize-y"
          />
          <Button onClick={send} disabled={pending}>
            Send
          </Button>
        </div>
      </div>
    </div>
  );
}

function FeedbackForm({ onSubmit }) {
  const [value, setValue] = useState("");
  return (
    <div className="mt-2.5 flex flex-col gap-1.5 rounded-md bg-muted p-2.5">
      <Input
        placeholder="What should it have said instead?"
        value={value}
        onChange={(e) => setValue(e.target.value)}
      />
      <div>
        <Button variant="secondary" size="sm" onClick={() => onSubmit(value)}>
          Submit correction
        </Button>
      </div>
    </div>
  );
}
