// Parses feedback_log.md entries of the form:
// ## 2026-07-04 14:32 — status: unprocessed
// Q: "..."
// Bad answer: "..."
// Correction: "..."
export function parseFeedbackLog(content) {
  if (!content) return [];
  const blocks = content.split(/\n(?=## )/).filter((b) => b.trim().startsWith("## "));
  return blocks.map((block) => {
    const headerMatch = block.match(/^##\s*(.+?)\s*—\s*status:\s*(\w+)/);
    const qMatch = block.match(/Q:\s*"([\s\S]*?)"\s*(?:\n|$)/);
    const badMatch = block.match(/Bad answer:\s*"([\s\S]*?)"\s*(?:\n|$)/);
    const correctionMatch = block.match(/Correction:\s*"([\s\S]*?)"\s*(?:\n|$)/);
    return {
      date: headerMatch ? headerMatch[1] : null,
      status: headerMatch ? headerMatch[2] : "unknown",
      question: qMatch ? qMatch[1] : null,
      badAnswer: badMatch ? badMatch[1] : null,
      correction: correctionMatch ? correctionMatch[1] : null,
      raw: block.trim(),
    };
  });
}

// Parses lessons.md sections of the form:
// ## Section Name
// - lesson one
// - lesson two, soft-wrapped onto an
//   indented continuation line
export function parseLessons(content) {
  if (!content) return [];
  const sections = content.split(/\n(?=## )/).filter((b) => b.trim().startsWith("## "));
  return sections
    .map((section) => {
      const lines = section.split("\n");
      const title = lines[0].replace(/^##\s*/, "").trim();
      const items = [];
      for (const line of lines.slice(1)) {
        if (/^-\s+/.test(line)) {
          items.push(line.replace(/^-\s*/, "").trim());
        } else if (line.trim() && items.length > 0) {
          items[items.length - 1] += " " + line.trim();
        }
      }
      return { title, items };
    })
    .filter((s) => s.items.length > 0);
}
