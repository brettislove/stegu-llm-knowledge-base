import React, { useEffect, useState } from "react";
import { useUser, UserButton } from "@clerk/clerk-react";
import { MessageSquare, Upload, Inbox, FolderOpen, Flag, BarChart3, Menu } from "lucide-react";
import { api } from "../api.js";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Sheet, SheetContent } from "@/components/ui/sheet";
import steguLogo from "@/assets/stegu-logo.svg";

const NAV_ITEMS = [
  { id: "ask", label: "Ptát se", icon: MessageSquare },
  { id: "ingest", label: "Nahrát", icon: Upload },
  { id: "pending-review", label: "Ke kontrole", icon: Inbox, showBadge: true },
  { id: "browse", label: "Prohlížet", icon: FolderOpen },
];

const MAINTENANCE_ITEMS = [
  { id: "feedback", label: "Zpětná vazba", icon: Flag },
  { id: "spend", label: "Náklady", icon: BarChart3 },
];

function NavButton({ item, active, onClick, pendingCount }) {
  const Icon = item.icon;
  return (
    <button
      onClick={onClick}
      className={cn(
        "flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2.5 text-left text-sm font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground",
        active && "bg-warn-tint text-primary font-semibold hover:bg-warn-tint hover:text-primary"
      )}
    >
      <Icon className="h-[17px] w-[17px] shrink-0" strokeWidth={1.6} />
      {item.label}
      {item.showBadge && pendingCount > 0 && (
        <Badge className="ml-auto px-1.5 py-0.5 text-[11px] font-bold leading-none">{pendingCount}</Badge>
      )}
    </button>
  );
}

function NavContent({ tab, go, pendingCount, user }) {
  return (
    <div className="flex h-full flex-col overflow-hidden bg-card px-4 pb-4 pt-[22px]">
      <div className="flex flex-col gap-1 px-1">
        <img src={steguLogo} alt="Stegu" className="h-[22px] w-auto" />
        <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
          Interní panel · wiki
        </span>
      </div>

      <nav className="mt-6 flex flex-col gap-0.5">
        {NAV_ITEMS.map((item) => (
          <NavButton
            key={item.id}
            item={item}
            active={tab === item.id}
            onClick={() => go(item.id)}
            pendingCount={pendingCount}
          />
        ))}

        <div className="px-2.5 pb-1.5 pt-3.5 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
          Údržba
        </div>
        {MAINTENANCE_ITEMS.map((item) => (
          <NavButton key={item.id} item={item} active={tab === item.id} onClick={() => go(item.id)} />
        ))}
      </nav>

      <div className="flex-1" />

      <div className="flex items-center gap-2.5 border-t border-border pt-3.5">
        <UserButton appearance={{ elements: { userButtonAvatarBox: "h-7 w-7" } }} />
        <div className="flex min-w-0 flex-col leading-tight">
          <span className="truncate text-[12.5px] font-semibold text-foreground">
            {user?.fullName || user?.username || "Přihlášený uživatel"}
          </span>
          <span className="truncate text-[11px] text-muted-foreground">
            {user?.primaryEmailAddress?.emailAddress || ""}
          </span>
        </div>
      </div>
    </div>
  );
}

export default function Sidebar({ tab, setTab }) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [pendingCount, setPendingCount] = useState(0);
  const { user } = useUser();

  useEffect(() => {
    let cancelled = false;
    api
      .getPendingReview()
      .then(({ items }) => {
        if (!cancelled) setPendingCount(items.length);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
    // Refetch whenever the active tab changes — cheap, and keeps the badge
    // accurate right after approving/rejecting an item elsewhere.
  }, [tab]);

  function go(nextTab) {
    setTab(nextTab);
    setMobileOpen(false);
  }

  return (
    <>
      <aside className="h-full w-[232px] shrink-0 border-r border-border mobile:hidden">
        <NavContent tab={tab} go={go} pendingCount={pendingCount} user={user} />
      </aside>

      <button
        onClick={() => setMobileOpen(true)}
        aria-label="Otevřít menu"
        className="fixed left-4 top-4 z-40 hidden h-9 w-9 items-center justify-center rounded-lg border border-border bg-card shadow-brand mobile:flex"
      >
        <Menu className="h-[18px] w-[18px]" strokeWidth={1.8} />
      </button>

      <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
        <SheetContent>
          <NavContent tab={tab} go={go} pendingCount={pendingCount} user={user} />
        </SheetContent>
      </Sheet>
    </>
  );
}
