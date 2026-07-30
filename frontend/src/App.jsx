import React, { useState } from "react";
import { SignedIn, SignedOut, SignIn } from "@clerk/clerk-react";
import Sidebar from "./components/Sidebar.jsx";
import ChatPanel from "./components/ChatPanel.jsx";
import IngestPanel from "./components/IngestPanel.jsx";
import PendingReviewPanel from "./components/PendingReviewPanel.jsx";
import BrowsePanel from "./components/BrowsePanel.jsx";
import ReviewPanel from "./components/ReviewPanel.jsx";
import SpendPanel from "./components/SpendPanel.jsx";
import ThemeToggle from "./components/ThemeToggle.jsx";
import steguLogo from "./assets/stegu-logo.svg";
import { cn } from "@/lib/utils";

export default function App() {
  const [tab, setTab] = useState("ask");
  const [browsePath, setBrowsePath] = useState(null);

  // Citation chips in ChatPanel call this to jump straight to the file
  // they cited, instead of feeding an always-visible side panel — the IA
  // change chosen over the prior CitedPagesPanel/FileViewerModal pair.
  function openInBrowse(path) {
    setBrowsePath(path);
    setTab("browse");
  }

  return (
    <>
      <ThemeToggle />
      <SignedOut>
        <div className="flex min-h-screen items-center justify-center bg-primary p-6">
          <div className="w-full max-w-md rounded-xl bg-card p-10 shadow-brand">
            <div className="mb-6 flex flex-col items-center gap-1.5 text-center">
              <img src={steguLogo} alt="Stegu" className="h-8 w-auto" />
              <span className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                LLM Wiki
              </span>
            </div>
            {/* Scoped to this instance only — the provider-level
                appearance (main.jsx) keeps Clerk's normal card chrome,
                which the UserButton popover in Sidebar.jsx also relies
                on. Stripping it there breaks that popover's floating-card
                styling. Here, embedded inside our own branded card, the
                chrome would double up and overflow on mobile, so this
                instance forces it to flow as plain full-width content. */}
            <SignIn
              appearance={{
                elements: {
                  rootBox: "w-full px-5",
                  // The dark baseTheme (main.jsx) puts its own drop shadow
                  // on cardBox specifically, not card — missing it here is
                  // what read as a second nested card floating inside ours.
                  cardBox: "w-full px-1 shadow-none",
                  card: "w-full shadow-none border-0 bg-transparent p-0",
                },
              }}
            />
          </div>
        </div>
      </SignedOut>

      <SignedIn>
        <div className="flex h-screen overflow-hidden mobile:flex-col">
          <Sidebar tab={tab} setTab={setTab} />
          <div className="min-h-0 min-w-0 flex-1 overflow-hidden">
            {/* Kept mounted (just hidden) instead of conditionally rendered
                like the other tabs — those refetch fresh on every visit and
                have nothing to lose, but ChatPanel's message history and
                in-session memory live in its own local state, and would be
                wiped every time a citation chip sends the user to Prohlížet
                and back if it were unmounted in between. */}
            <div className={cn("h-full", tab !== "ask" && "hidden")}>
              <ChatPanel onOpenInBrowse={openInBrowse} />
            </div>
            {tab === "ingest" && <IngestPanel />}
            {tab === "pending-review" && <PendingReviewPanel />}
            {tab === "browse" && <BrowsePanel initialPath={browsePath} />}
            {tab === "feedback" && <ReviewPanel />}
            {tab === "spend" && <SpendPanel />}
          </div>
        </div>
      </SignedIn>
    </>
  );
}
