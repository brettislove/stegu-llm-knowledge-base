import React, { useEffect, useState } from "react";
import { SignedIn, SignedOut, SignIn } from "@clerk/clerk-react";
import Sidebar from "./components/Sidebar.jsx";
import HomePanel from "./components/HomePanel.jsx";
import ChatPanel from "./components/ChatPanel.jsx";
import IngestPanel from "./components/IngestPanel.jsx";
import PendingReviewPanel from "./components/PendingReviewPanel.jsx";
import BrowsePanel from "./components/BrowsePanel.jsx";
import ReviewPanel from "./components/ReviewPanel.jsx";
import SpendPanel from "./components/SpendPanel.jsx";
import ThemeToggle from "./components/ThemeToggle.jsx";
import steguLogo from "./assets/stegu-logo.svg";
import { cn } from "@/lib/utils";

const VALID_TABS = ["home", "ask", "ingest", "pending-review", "browse", "feedback", "spend"];
const DEFAULT_TAB = "home";

function readTabFromUrl() {
  const tab = new URLSearchParams(window.location.search).get("tab");
  return VALID_TABS.includes(tab) ? tab : DEFAULT_TAB;
}

export default function App() {
  const [tab, setTabState] = useState(readTabFromUrl);
  const [browsePath, setBrowsePath] = useState(null);
  const [pendingQuestion, setPendingQuestion] = useState(null);

  // Keeps the active tab in the URL (query param, not a path, since there's
  // no SPA-fallback rewrite configured on the static host) so a reload or a
  // shared link lands back on the same panel instead of always on Chat.
  function setTab(nextTab) {
    setTabState(nextTab);
    const params = new URLSearchParams(window.location.search);
    if (nextTab === DEFAULT_TAB) {
      params.delete("tab");
    } else {
      params.set("tab", nextTab);
    }
    const query = params.toString();
    window.history.pushState({ tab: nextTab }, "", query ? `?${query}` : window.location.pathname);
  }

  useEffect(() => {
    function handlePopState() {
      setTabState(readTabFromUrl());
    }
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  // Citation chips in ChatPanel call this to jump straight to the file
  // they cited, instead of feeding an always-visible side panel — the IA
  // change chosen over the prior CitedPagesPanel/FileViewerModal pair.
  function openInBrowse(path) {
    setBrowsePath(path);
    setTab("browse");
  }

  // Domů's quick-ask bar calls this to fire a question straight into Chat.
  function askInChat(question) {
    setPendingQuestion(question);
    setTab("ask");
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
              <ChatPanel
                onOpenInBrowse={openInBrowse}
                initialQuestion={pendingQuestion}
                onConsumeInitialQuestion={() => setPendingQuestion(null)}
              />
            </div>
            {tab === "home" && <HomePanel onNavigate={setTab} onAsk={askInChat} />}
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
