import React, { useState } from "react";
import { SignedIn, SignedOut, SignIn, UserButton } from "@clerk/clerk-react";
import Sidebar from "./components/Sidebar.jsx";
import ChatPanel from "./components/ChatPanel.jsx";
import IngestPanel from "./components/IngestPanel.jsx";
import ReviewPanel from "./components/ReviewPanel.jsx";
import CitedPagesPanel from "./components/CitedPagesPanel.jsx";
import FileViewerModal from "./components/FileViewerModal.jsx";

export default function App() {
  const [tab, setTab] = useState("ask");
  const [citedPaths, setCitedPaths] = useState([]);
  const [openFile, setOpenFile] = useState(null);

  function addCitedPaths(paths) {
    setCitedPaths((prev) => [...new Set([...paths, ...prev])].slice(0, 8));
  }

  return (
    <>
      <SignedOut>
        <div className="grid h-screen place-items-center">
          <SignIn />
        </div>
      </SignedOut>

      <SignedIn>
        <div className="grid h-screen grid-cols-[220px_1fr_300px] overflow-hidden mobile:h-auto mobile:min-h-screen mobile:grid-cols-1 mobile:grid-rows-[auto_1fr_auto]">
          <div className="min-h-0 overflow-hidden mobile:max-h-[260px]">
            <Sidebar tab={tab} setTab={setTab} onOpenFile={setOpenFile} />
          </div>

          <div className="min-h-0 min-w-0 overflow-hidden">
            {tab === "ask" && <ChatPanel onCitedPaths={addCitedPaths} />}
            {tab === "ingest" && <IngestPanel />}
            {tab === "review" && <ReviewPanel />}
          </div>

          <div className="min-h-0 overflow-hidden mobile:max-h-[260px]">
            <CitedPagesPanel paths={citedPaths} />
          </div>

          <div className="fixed bottom-3 right-3">
            <UserButton />
          </div>

          <FileViewerModal path={openFile} open={!!openFile} onOpenChange={(v) => !v && setOpenFile(null)} />
        </div>
      </SignedIn>
    </>
  );
}
