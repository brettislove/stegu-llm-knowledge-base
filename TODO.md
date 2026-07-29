# TODO

Backend-engineering items from the Design Notes audit that are deliberately
deferred, not forgotten. Not agent-facing — see `SCHEMA.md` for wiki
conventions agents actually read.

- **Git layer over the OneDrive-backed wiki, for diffing** — undecided.
  Design notes call for a git layer on top of OneDrive's built-in version
  history; not started.

- **Single-writer enforcement beyond convention** — the Graph app
  registration holds `Files.ReadWrite.All`, with no separate read-only
  credential/role carved out for Claude Cowork or any future read-only
  consumer. Today "only the ingestion pipeline writes" is convention, not
  something Graph permissions actually enforce.

- **`access` permission filtering is prompt-instruction only** — enforced
  today via `query_agent.py`'s `PUBLIC_RULE`/`INTERNAL_RULE` system-prompt
  text, not a code-level filter on `read_file`/`grep` results by the
  `access` frontmatter field. An agent that ignores the instruction (or a
  prompt-injected page) isn't actually blocked.

- **Prompt caching boundary** — `cache_control` is anchored on SCHEMA.md +
  tool defs (see `agentic_loop.py`), not specifically on root+domain index
  content as the design notes describe. Worth revisiting once there's a
  measurable latency/cost reason to.

- **`tags` / `version` frontmatter fields** — scaffolded in
  `frontmatter.py`'s `FIELD_ORDER` and the schema, but no agent populates
  them. Fine for now; revisit when there's an actual cross-cutting search
  or versioning use case.

- **`quickXorHash` as an alternative/additional Graph hash source** — only
  `sha256Hash` is wired up (see `graph_client.extract_content_hash`)
  because it needs zero format migration from the existing `sha256:<hex>`
  convention. If `sha256Hash` turns out to be unreliable/absent in
  practice on the real tenant, `quickXorHash` is Graph's more universally
  populated hash for OneDrive for Business, but implementing it means a
  standalone algorithm (not in any stdlib/common package) plus a manifest
  migration.

(Per-category archive retention policy for `pravo-a-admin`/`certifikace`
vs. the rest is already tracked in `SCHEMA.md` §12 — not duplicated here.)
