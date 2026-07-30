import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";

const DAY_LABELS = ["Ne", "Po", "Út", "St", "Čt", "Pá", "So"];

// The backend logs "classify" and "ingest" as separate spend records (one
// per API call), but the dashboard groups them into one "Nahrání" row —
// same 3-group breakdown as the mockup (Dotazy / Nahrání / Údržba).
const GROUPS = [
  { label: "Dotazy (Ptát se)", keys: ["query"] },
  { label: "Nahrání (Nahrát)", keys: ["classify", "ingest"] },
  { label: "Údržba (lint, distill, split)", keys: ["distill", "lint", "split"] },
];

function groupByAction(byAction) {
  return GROUPS.map((g) => {
    const totals = g.keys.reduce(
      (acc, k) => {
        const b = byAction[k];
        if (!b) return acc;
        return {
          count: acc.count + b.count,
          cache_tokens: acc.cache_tokens + b.cache_tokens,
          new_tokens: acc.new_tokens + b.new_tokens,
          cost_czk: acc.cost_czk + b.cost_czk,
        };
      },
      { count: 0, cache_tokens: 0, new_tokens: 0, cost_czk: 0 }
    );
    return { label: g.label, ...totals };
  }).filter((g) => g.count > 0);
}

function KpiCard({ label, value, unit, sub }) {
  return (
    <div className="rounded-lg border border-border bg-card p-5 shadow-brand">
      <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div className="font-body text-[29px] font-extrabold tracking-tight text-gold-dark tabular-nums">
        {value}
        {unit && <small className="ml-1 text-sm font-semibold text-muted-foreground">{unit}</small>}
      </div>
      {sub && <div className="mt-1 text-xs text-muted-foreground">{sub}</div>}
    </div>
  );
}

export default function SpendPanel() {
  const [range, setRange] = useState("week");
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    api
      .getSpend(range)
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch((e) => {
        if (!cancelled) setError(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, [range]);

  const groups = data ? groupByAction(data.by_action) : [];
  const maxDaily = data ? Math.max(1, ...data.daily.map((d) => d.cost_czk)) : 1;

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="flex items-center justify-between gap-4 border-b border-border bg-card px-10 py-6 pr-24 mobile:flex-col mobile:items-start mobile:gap-3 mobile:pl-16">
        <h2 className="font-display text-[26px] font-bold text-foreground">Náklady a využití</h2>
        <Tabs value={range} onValueChange={setRange}>
          <TabsList>
            <TabsTrigger value="today">Dnes</TabsTrigger>
            <TabsTrigger value="week">Tento týden</TabsTrigger>
            <TabsTrigger value="month">Tento měsíc</TabsTrigger>
          </TabsList>
        </Tabs>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-10 py-7 mobile:px-4">
        <div className="mx-auto max-w-[1040px]">
          {error && <p className="text-sm text-[hsl(var(--restricted))]">Chyba: {error}</p>}
          {!data && !error && <p className="text-sm text-muted-foreground">Načítání…</p>}

          {data && (
            <>
              <div className="mb-7 grid grid-cols-[repeat(auto-fit,minmax(190px,1fr))] gap-3.5">
                <KpiCard label="Odhadovaná cena" value={data.total_cost_czk} unit="Kč" sub={`za ${data.action_count} volání API`} />
                <KpiCard
                  label="Tokeny celkem"
                  value={Math.round(data.total_tokens / 1000)}
                  unit="tis."
                  sub="vstup + výstup + cache"
                />
                <KpiCard label="Podíl z cache" value={data.cache_pct} unit="%" sub="SCHEMA.md a nástroje se nenačítají znovu" />
                <KpiCard
                  label="Dotazy / Nahrání"
                  value={data.by_action.query?.count || 0}
                  unit={`/ ${data.by_action.ingest?.count || 0}`}
                  sub="v tomto období"
                />
              </div>

              <h3 className="mb-3.5 font-display text-lg font-bold text-foreground">
                Vývoj za posledních 7 dní
              </h3>
              <div className="mb-7 rounded-lg border border-border bg-card p-5 pb-4 shadow-brand">
                <div className="mb-4 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                  Odhad Kč / den
                </div>
                <div className="flex h-24 items-end gap-2 border-b border-border">
                  {data.daily.map((d, i) => {
                    const isToday = i === data.daily.length - 1;
                    const heightPct = Math.max(4, Math.round((d.cost_czk / maxDaily) * 100));
                    return (
                      <div key={d.date} className="flex h-full flex-1 flex-col items-center justify-end">
                        <div
                          title={`${d.date}: ${d.cost_czk} Kč`}
                          style={{ height: `${heightPct}%` }}
                          className={cn(
                            "w-full max-w-[34px] rounded-t",
                            isToday ? "bg-gold" : "bg-gold-tint-border"
                          )}
                        />
                      </div>
                    );
                  })}
                </div>
                <div className="mt-2 flex gap-2">
                  {data.daily.map((d, i) => (
                    <span
                      key={d.date}
                      className={cn(
                        "flex-1 text-center text-[10.5px] text-muted-foreground",
                        i === data.daily.length - 1 && "font-bold text-gold-dark"
                      )}
                    >
                      {DAY_LABELS[new Date(d.date).getDay()]}
                    </span>
                  ))}
                </div>
              </div>

              <h3 className="mb-3.5 font-display text-lg font-bold text-foreground">Podle typu akce</h3>
              <div className="mb-3 flex gap-4">
                <span className="inline-flex items-center gap-1.5 text-[11.5px] text-muted-foreground">
                  <span className="h-2 w-2 rounded-sm bg-chart-cache" />Z cache (levnější)
                </span>
                <span className="inline-flex items-center gap-1.5 text-[11.5px] text-muted-foreground">
                  <span className="h-2 w-2 rounded-sm bg-chart-new" />Nové (plná cena)
                </span>
              </div>
              <div className="overflow-x-auto rounded-lg border border-border shadow-brand">
                <table className="w-full border-collapse">
                  <thead>
                    <tr className="bg-foreground text-background">
                      <th className="px-4 py-2.5 text-left text-[10.5px] font-semibold uppercase tracking-wide">Akce</th>
                      <th className="px-4 py-2.5 text-left text-[10.5px] font-semibold uppercase tracking-wide">Počet</th>
                      <th className="px-4 py-2.5 text-left text-[10.5px] font-semibold uppercase tracking-wide">Poměr</th>
                      <th className="px-4 py-2.5 text-left text-[10.5px] font-semibold uppercase tracking-wide">Odhad Kč</th>
                    </tr>
                  </thead>
                  <tbody className="bg-card">
                    {groups.map((g, i) => {
                      const total = g.cache_tokens + g.new_tokens;
                      const cachePct = total ? Math.round((g.cache_tokens / total) * 100) : 0;
                      return (
                        <tr key={g.label} className={i > 0 ? "border-t border-border" : ""}>
                          <td className="px-4 py-3 text-[13.5px] font-semibold text-foreground">{g.label}</td>
                          <td className="px-4 py-3 text-[13.5px] tabular-nums text-foreground">{g.count}</td>
                          <td className="px-4 py-3">
                            <div className="flex items-center gap-2">
                              <div className="flex h-2 w-36 overflow-hidden rounded-full bg-border">
                                <div className="h-full bg-chart-cache" style={{ width: `${cachePct}%` }} />
                                <div className="h-full bg-chart-new" style={{ width: `${100 - cachePct}%` }} />
                              </div>
                              <span className="text-[11.5px] tabular-nums text-muted-foreground">{cachePct}&nbsp;%</span>
                            </div>
                          </td>
                          <td className="px-4 py-3 text-[13.5px] tabular-nums text-foreground">{g.cost_czk.toFixed(2)}&nbsp;Kč</td>
                        </tr>
                      );
                    })}
                    {groups.length === 0 && (
                      <tr>
                        <td colSpan={4} className="px-4 py-4 text-[13px] text-muted-foreground">
                          Zatím žádná data za toto období.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>

              <div className="mt-6 rounded-md border-l-[3px] border-l-gold bg-gold-tint px-4 py-3.5">
                <div className="mb-1 text-[11px] font-bold uppercase tracking-wide text-gold-dark">
                  Kde šetříme
                </div>
                <p className="text-[13.5px] leading-relaxed text-muted-foreground">
                  SCHEMA.md a definice nástrojů se u každého volání čtou z mezipaměti — {data.cache_pct}&nbsp;%
                  tokenů v tomto období bylo z cache za desetinovou cenu.
                </p>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
