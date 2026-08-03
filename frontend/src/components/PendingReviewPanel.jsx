import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import { Button } from "@/components/ui/button";
import { Badge, BadgeDot } from "@/components/ui/badge";
import LoadingNotice from "@/components/ui/loading-notice";
import { FileText } from "lucide-react";

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

const ACCESS_OPTIONS = ["public", "internal", "restricted"];

function ReviewCard({ item, onDecided }) {
  const [category, setCategory] = useState(item.classification.category);
  const [topic, setTopic] = useState(item.classification.topic || "");
  const [access, setAccess] = useState(item.classification.access);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function approve() {
    setBusy(true);
    setError(null);
    try {
      await api.approvePendingReview(item.id, { category, topic, access });
      onDecided(item.id);
    } catch (e) {
      setError(e.message);
      setBusy(false);
    }
  }

  async function reject() {
    setBusy(true);
    setError(null);
    try {
      await api.rejectPendingReview(item.id);
      onDecided(item.id);
    } catch (e) {
      setError(e.message);
      setBusy(false);
    }
  }

  return (
    <div className="mb-4 rounded-lg border border-border bg-card p-5 shadow-brand">
      <div className="mb-3 flex items-start justify-between gap-4">
        <div className="flex items-center gap-2.5 text-sm font-semibold text-foreground">
          <FileText className="h-4 w-4 shrink-0 text-muted-foreground" strokeWidth={1.5} />
          {item.filename}
        </div>
        <Badge variant="warn" className="shrink-0">
          <BadgeDot />
          Nízká jistota
        </Badge>
      </div>

      {item.classification.reasoning && (
        <p className="mb-4 border-l-2 border-border pl-3 font-display text-sm italic text-muted-foreground">
          „{item.classification.reasoning}“
        </p>
      )}

      <div className="mb-4 grid grid-cols-[repeat(auto-fit,minmax(150px,1fr))] gap-2.5">
        <label className="flex flex-col gap-1">
          <span className="text-[10.5px] font-semibold uppercase tracking-wide text-muted-foreground">
            Kategorie
          </span>
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            className="rounded-md border border-border bg-card px-2.5 py-2 text-[13.5px] text-foreground"
          >
            {CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-[10.5px] font-semibold uppercase tracking-wide text-muted-foreground">
            Téma
          </span>
          <input
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder="— žádné —"
            className="rounded-md border border-border bg-card px-2.5 py-2 text-[13.5px] text-foreground"
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-[10.5px] font-semibold uppercase tracking-wide text-muted-foreground">
            Přístup
          </span>
          <select
            value={access}
            onChange={(e) => setAccess(e.target.value)}
            className="rounded-md border border-border bg-card px-2.5 py-2 text-[13.5px] text-foreground"
          >
            {ACCESS_OPTIONS.map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>
        </label>
      </div>

      {error && <p className="mb-3 text-[12.5px] text-[hsl(var(--restricted))]">Chyba: {error}</p>}

      <div className="flex gap-2.5">
        <Button variant="success" size="sm" onClick={approve} disabled={busy}>
          Schválit
        </Button>
        <Button variant="outline" size="sm" onClick={reject} disabled={busy}>
          Zamítnout
        </Button>
      </div>
    </div>
  );
}

export default function PendingReviewPanel() {
  const [items, setItems] = useState(null);
  const [error, setError] = useState(null);

  function refresh() {
    api
      .getPendingReview()
      .then((res) => setItems(res.items))
      .catch((e) => setError(e.message));
  }

  useEffect(refresh, []);

  function handleDecided(id) {
    setItems((prev) => prev.filter((i) => i.id !== id));
  }

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="flex items-center justify-between gap-4 border-b border-border bg-card px-10 py-6 pr-24 mobile:pl-16">
        <h2 className="font-display text-[26px] font-bold text-foreground">Ke kontrole</h2>
        {items && items.length > 0 && (
          <Badge variant="warn">
            <BadgeDot />
            {items.length} čekají na schválení
          </Badge>
        )}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-10 py-7 mobile:px-4">
        <div className="mx-auto max-w-[1040px]">
          {error && <p className="text-sm text-[hsl(var(--restricted))]">Chyba: {error}</p>}
          {items === null && !error && <LoadingNotice />}
          {items && items.length === 0 && (
            <p className="text-sm text-muted-foreground">
              Žádné položky nečekají na kontrolu.
            </p>
          )}
          {items?.map((item) => (
            <ReviewCard key={item.id} item={item} onDecided={handleDecided} />
          ))}
        </div>
      </div>
    </div>
  );
}
