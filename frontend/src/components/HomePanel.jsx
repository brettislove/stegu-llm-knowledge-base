import React, { useEffect, useState } from "react";
import { useUser } from "@clerk/clerk-react";
import { api } from "../api.js";
import { parseFeedbackLog } from "@/lib/parseWiki";
import { Badge, BadgeDot } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import LoadingNotice, { LoadingNoticeCompact } from "@/components/ui/loading-notice";
import { Upload, Inbox, FolderOpen, Flag, BarChart3, Send, FileText, MessageSquareWarning } from "lucide-react";
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

function Sparkline({ daily }) {
  if (!daily || daily.length < 2) return null;
  const values = daily.map((d) => d.cost_czk);
  const max = Math.max(...values, 0.01);
  const w = 64;
  const h = 26;
  const step = w / (values.length - 1);
  const points = values.map((v, i) => [i * step, h - (v / max) * (h - 4) - 2]);
  const line = points.map((p) => p.join(",")).join(" L ");
  const area = `M ${points[0].join(",")} L ${line} L ${w},${h} L 0,${h} Z`;
  const last = points[points.length - 1];
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} className="shrink-0 text-gold" fill="none">
      <path d={area} fill="currentColor" opacity="0.15" />
      <path d={`M ${points[0].join(",")} L ${line}`} stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={last[0]} cy={last[1]} r="2.3" fill="currentColor" />
    </svg>
  );
}

function Tile({ icon: Icon, label, desc, onClick, children }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex w-full flex-col rounded-lg border border-border bg-card p-[18px] text-left shadow-brand transition-all hover:-translate-y-0.5 hover:border-[hsl(var(--gold-tint-border))] hover:shadow-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <div className="mb-2 flex items-center gap-2.5">
        <span className="flex h-[30px] w-[30px] shrink-0 items-center justify-center rounded-md bg-warn-tint text-primary">
          <Icon className="h-[17px] w-[17px]" strokeWidth={1.7} />
        </span>
        <span className="font-display text-base font-semibold text-foreground">{label}</span>
      </div>
      <p className="min-h-[38px] text-[12.5px] leading-relaxed text-muted-foreground">{desc}</p>
      <div className="mt-3.5 flex items-end justify-between gap-2.5 border-t border-border pt-3">{children}</div>
    </button>
  );
}

function Stat({ value, unit, sub }) {
  return (
    <div>
      <div className="font-body text-2xl font-extrabold tracking-tight text-foreground tabular-nums">
        {value}
        {unit && <small className="ml-1 text-xs font-semibold text-muted-foreground">{unit}</small>}
      </div>
      {sub && <div className="mt-0.5 text-[11px] text-muted-foreground">{sub}</div>}
    </div>
  );
}

export default function HomePanel({ onNavigate, onAsk }) {
  const { user } = useUser();
  const [question, setQuestion] = useState("");
  const [pendingItems, setPendingItems] = useState(null);
  const [pageStats, setPageStats] = useState(null);
  const [feedbackEntries, setFeedbackEntries] = useState(null);
  const [spend, setSpend] = useState(null);

  useEffect(() => {
    let cancelled = false;

    api
      .getPendingReview()
      .then(({ items }) => !cancelled && setPendingItems(items))
      .catch(() => !cancelled && setPendingItems([]));

    api
      .getSpend("month")
      .then((res) => !cancelled && setSpend(res))
      .catch(() => {});

    api
      .getFile("feedback_log.md")
      .then(({ content }) => {
        if (cancelled) return;
        setFeedbackEntries(parseFeedbackLog(content).filter((e) => e.status === "unprocessed"));
      })
      .catch(() => !cancelled && setFeedbackEntries([]));

    Promise.all(CATEGORIES.map((cat) => api.listFiles(cat).then((r) => r.files.length).catch(() => 0))).then(
      (counts) => {
        if (cancelled) return;
        setPageStats({
          pages: counts.reduce((a, b) => a + b, 0),
          categories: counts.filter((c) => c > 0).length,
        });
      }
    );

    return () => {
      cancelled = true;
    };
  }, []);

  function submitAsk(e) {
    e.preventDefault();
    const q = question.trim();
    if (!q) return;
    onAsk(q);
    setQuestion("");
  }

  const attentionItems = [
    ...(pendingItems || []).slice(0, 3).map((item) => ({
      key: `pr-${item.id}`,
      icon: FileText,
      text: (
        <>
          Dokument <b className="font-semibold text-foreground">„{item.filename}“</b> čeká na schválení.
        </>
      ),
      onClick: () => onNavigate("pending-review"),
    })),
    ...(feedbackEntries || []).slice(0, 3).map((entry, i) => ({
      key: `fb-${i}`,
      icon: MessageSquareWarning,
      text: (
        <>
          Nevyřešená připomínka: <b className="font-semibold text-foreground">„{entry.question || "bez popisu"}“</b>
        </>
      ),
      onClick: () => onNavigate("feedback"),
    })),
  ];

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="flex items-center justify-between gap-4 border-b border-border bg-card px-10 py-6 pr-24 mobile:flex-col mobile:items-start mobile:gap-1 mobile:pl-16">
        <h2 className="font-display text-[26px] font-bold text-foreground">Domů</h2>
        <span className="text-[12.5px] text-muted-foreground">
          {new Date().toLocaleDateString("cs-CZ", { weekday: "long", day: "numeric", month: "long", year: "numeric" })}
        </span>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-10 py-7 mobile:px-4">
        <div className="mx-auto max-w-[1040px]">
          <p className="mb-3.5 font-display text-lg font-semibold text-foreground">
            Dobrý den{user?.firstName ? `, ${user.firstName}` : ""}.
          </p>

          <form
            onSubmit={submitAsk}
            className="mb-6 flex items-center gap-2.5 rounded-xl border border-border bg-card px-4 py-3 shadow-brand focus-within:ring-1 focus-within:ring-ring"
          >
            <Input
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="Zeptejte se na cokoliv ze znalostní báze…"
              className="h-9 flex-1 border-0 bg-transparent px-0 text-[15px] shadow-none focus-visible:ring-0"
            />
            <Button type="submit" size="sm" disabled={!question.trim()} className="shrink-0 gap-1.5">
              <Send className="h-3.5 w-3.5" />
              Zeptat se
            </Button>
          </form>

          <div className="grid grid-cols-[repeat(auto-fit,minmax(230px,1fr))] gap-3.5">
            <Tile icon={Upload} label="Nahrát" desc="Přidejte nové dokumenty do znalostní báze." onClick={() => onNavigate("ingest")}>
              <span className="text-[11.5px] font-medium text-muted-foreground">Přetáhněte soubor nebo klikněte pro výběr</span>
            </Tile>

            <Tile
              icon={Inbox}
              label="Ke kontrole"
              desc="Odpovědi čekající na schválení před publikací."
              onClick={() => onNavigate("pending-review")}
            >
              {pendingItems === null ? (
                <LoadingNoticeCompact />
              ) : pendingItems.length > 0 ? (
                <Badge variant="warn">
                  <BadgeDot />
                  {pendingItems.length} čekají na schválení
                </Badge>
              ) : (
                <span className="text-[11.5px] text-muted-foreground">Žádné položky nečekají</span>
              )}
            </Tile>

            <Tile icon={FolderOpen} label="Prohlížet" desc="Procházejte strukturu znalostní báze podle složek." onClick={() => onNavigate("browse")}>
              {pageStats ? (
                <Stat value={pageStats.pages} unit="stránek" sub={`${pageStats.categories} kategorií`} />
              ) : (
                <LoadingNoticeCompact />
              )}
            </Tile>

            <Tile
              icon={Flag}
              label="Zpětná vazba"
              desc="Nahlášené nebo problematické odpovědi k prošetření."
              onClick={() => onNavigate("feedback")}
            >
              {feedbackEntries === null ? (
                <LoadingNoticeCompact />
              ) : feedbackEntries.length > 0 ? (
                <Badge variant="info">{feedbackEntries.length} nevyřešených připomínek</Badge>
              ) : (
                <span className="text-[11.5px] text-muted-foreground">Žádné nevyřešené připomínky</span>
              )}
            </Tile>

            <Tile icon={BarChart3} label="Náklady" desc="Přehled nákladů na LLM dotazy a zpracování." onClick={() => onNavigate("spend")}>
              {spend ? (
                <>
                  <Stat value={spend.total_cost_czk} unit="Kč" sub={`za ${spend.action_count} volání API tento měsíc`} />
                  <Sparkline daily={spend.daily} />
                </>
              ) : (
                <LoadingNoticeCompact />
              )}
            </Tile>
          </div>

          <h3 className="mb-3.5 mt-8 font-display text-lg font-bold text-foreground">Vyžaduje pozornost</h3>
          <div className="overflow-hidden rounded-lg border border-border bg-card shadow-brand">
            {pendingItems === null || feedbackEntries === null ? (
              <LoadingNotice className="px-[18px] py-4" />
            ) : attentionItems.length === 0 ? (
              <p className="px-[18px] py-4 text-[13px] text-muted-foreground">Nic nečeká na vaši pozornost.</p>
            ) : (
              attentionItems.map((item, i) => (
                <button
                  key={item.key}
                  type="button"
                  onClick={item.onClick}
                  className={cn(
                    "flex w-full items-center gap-3 px-[18px] py-3.5 text-left transition-colors hover:bg-muted",
                    i > 0 && "border-t border-border"
                  )}
                >
                  <item.icon className="h-4 w-4 shrink-0 text-muted-foreground" strokeWidth={1.6} />
                  <span className="flex-1 text-[13.5px] text-foreground">{item.text}</span>
                </button>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
