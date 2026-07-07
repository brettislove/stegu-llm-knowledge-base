import React, { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Flag, CheckCircle2, User, Bot, Send } from "lucide-react";
import { cn } from "@/lib/utils";

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
    <div className="flex h-full flex-col bg-background">
      <div className="border-b border-border px-7 pb-3.5 pt-5 bg-card">
        <h1 className="font-display text-[22px] font-semibold tracking-tight">Ask the Knowledge Base</h1>
        <p className="mt-1 text-[13px] text-muted-foreground">
          Query the wiki directly, or draft an answer for a customer email.
        </p>
      </div>

      <div className="px-7 py-3 border-b border-border bg-muted/30">
        <Tabs value={mode} onValueChange={setMode} className="w-full max-w-[400px]">
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="internal">Internal Search</TabsTrigger>
            <TabsTrigger value="public">Draft Public Reply</TabsTrigger>
          </TabsList>
        </Tabs>
      </div>

      <ScrollArea className="flex-1 p-4 sm:p-7">
        <div className="mx-auto flex max-w-3xl flex-col gap-6 pb-12">
          {messages.map((m) => (
            <div key={m.id} className="flex gap-4 animate-fade-in">
              <Avatar className={cn("h-8 w-8 border", m.role === "user" ? "bg-muted" : "bg-primary text-primary-foreground")}>
                <AvatarFallback className="bg-transparent">
                  {m.role === "user" ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
                </AvatarFallback>
              </Avatar>
              
              <div className="flex-1 space-y-2 overflow-hidden">
                <div className="prose prose-sm dark:prose-invert max-w-none break-words leading-relaxed">
                  <div className="whitespace-pre-wrap">{m.text}</div>
                </div>

                {m.role === "agent" && !m.text.startsWith("Error:") && (
                  <div className="pt-2">
                    {m.feedbackSent ? (
                      <span className="inline-flex items-center gap-1.5 font-mono text-[11px] font-medium text-emerald-600 dark:text-emerald-500">
                        <CheckCircle2 className="h-3.5 w-3.5" />
                        Feedback recorded
                      </span>
                    ) : (
                      <button
                        className="inline-flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground transition-colors hover:text-foreground"
                        onClick={() => toggleFeedback(m.id)}
                      >
                        <Flag className="h-3.5 w-3.5" />
                        Flag incorrect answer
                      </button>
                    )}
                    {m.feedbackOpen && <FeedbackForm onSubmit={(c) => submitFeedback(m, c)} />}
                  </div>
                )}
              </div>
            </div>
          ))}

          {pending && (
            <div className="flex gap-4 animate-fade-in">
              <Avatar className="h-8 w-8 border bg-primary text-primary-foreground">
                <AvatarFallback className="bg-transparent">
                  <Bot className="h-4 w-4 animate-pulse" />
                </AvatarFallback>
              </Avatar>
              <div className="flex-1 space-y-2 py-1">
                <div className="flex gap-1">
                  <span className="h-2 w-2 rounded-full bg-muted-foreground animate-bounce [animation-delay:-0.3s]"></span>
                  <span className="h-2 w-2 rounded-full bg-muted-foreground animate-bounce [animation-delay:-0.15s]"></span>
                  <span className="h-2 w-2 rounded-full bg-muted-foreground animate-bounce"></span>
                </div>
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>
      </ScrollArea>

      <div className="p-4 sm:p-7 pt-0">
        <div className="mx-auto max-w-3xl relative flex items-center rounded-lg border border-input bg-background shadow-sm focus-within:ring-1 focus-within:ring-ring">
          <Textarea
            placeholder="Ask a question about the knowledge base..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
            className="min-h-[60px] w-full resize-none border-0 bg-transparent py-4 pl-4 pr-12 focus-visible:ring-0 sm:text-sm"
          />
          <Button 
            size="icon" 
            onClick={send} 
            disabled={pending || !input.trim()}
            className="absolute right-2 bottom-2 h-8 w-8 rounded-md"
          >
            <Send className="h-4 w-4" />
            <span className="sr-only">Send</span>
          </Button>
        </div>
        <p className="mt-2 text-center text-[11px] text-muted-foreground">
          AI agents can make mistakes. Always verify information before sending to clients.
        </p>
      </div>
    </div>
  );
}

function FeedbackForm({ onSubmit }) {
  const [value, setValue] = useState("");
  return (
    <div className="mt-3 flex flex-col gap-2 rounded-lg border border-border bg-muted/50 p-3 animate-in fade-in slide-in-from-top-2">
      <Input
        placeholder="What should the agent have said instead?"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        className="h-8 text-xs bg-background"
      />
      <div className="flex justify-end">
        <Button variant="secondary" size="sm" className="h-7 text-xs" onClick={() => onSubmit(value)}>
          Submit Correction
        </Button>
      </div>
    </div>
  );
}