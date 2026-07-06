import React from "react";
import { Badge } from "@/components/ui/badge";

export function parseAccess(content) {
  const match = content.match(/^access:\s*(\w+)/m);
  return match ? match[1] : "unknown";
}

export function parseFrontmatterField(content, field) {
  const match = content.match(new RegExp(`^${field}:\\s*(.+)$`, "m"));
  return match ? match[1].trim().replace(/^["']|["']$/g, "") : null;
}

const VARIANT_BY_ACCESS = {
  public: "public",
  internal: "internal",
  restricted: "restricted",
};

export default function AccessStamp({ access, className }) {
  if (!access || access === "unknown") return null;
  return (
    <Badge variant={VARIANT_BY_ACCESS[access] || "outline"} className={`stamp-badge shrink-0 -rotate-2 ${className || ""}`}>
      {access}
    </Badge>
  );
}
