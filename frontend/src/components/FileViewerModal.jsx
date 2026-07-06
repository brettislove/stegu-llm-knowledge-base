import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import { Badge } from "@/components/ui/badge";
import { parseAccess } from "./AccessStamp.jsx";
import { Dialog, DialogContent, DialogHeader, DialogBody } from "@/components/ui/dialog";

export default function FileViewerModal({ path, open, onOpenChange }) {
  const [content, setContent] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!path) return;
    let cancelled = false;
    setContent(null);
    setError(null);
    api
      .getFile(path)
      .then((res) => {
        if (!cancelled) setContent(res.content);
      })
      .catch((e) => {
        if (!cancelled) setError(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, [path]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <span className="break-all font-mono text-[12.5px]">{path}</span>
          {content && (
            <Badge
              variant={parseAccess(content)}
            >
              {parseAccess(content)}
            </Badge>
          )}
        </DialogHeader>
        <DialogBody>
          {error && <p className="text-[hsl(var(--restricted))]">Error: {error}</p>}
          {!error && content === null && <p className="text-muted-foreground">Loading…</p>}
          {content !== null && (
            <pre className="whitespace-pre-wrap font-mono text-[12.5px]">{content}</pre>
          )}
        </DialogBody>
      </DialogContent>
    </Dialog>
  );
}
