# SCHEMA.md — Knowledge Base Conventions

This document defines how the wiki is structured and how agents (classify,
ingest, query, distill, lint, split) are expected to read and write it. All
agents receive this file as part of their system context on every call.

**Runtime note:** this instance is OneDrive/Graph-API-backed — `wiki/`,
`raw/`, `pending_review/`, and `archive/` are folders in a business
OneDrive drive, read and written via Microsoft Graph, not local disk.
Single-writer discipline is enforced two ways: an in-process `asyncio.Lock`
(guards against the same backend process racing itself) and a real
`_system/ingest.lock` item written to OneDrive before a batch run and
deleted on completion (guards against two backend processes/deploys
racing each other) — see §5.

## 1. Directory layout — variable depth

Top-level folders mirror `VALID_CATEGORY` exactly:

```
wiki/
├── index.md               # root (Layer 1) catalog — kept short
├── manifest.json           # system bookkeeping (id/hash/token_count/parent per page) — never hand-edited
├── log.md                  # append-only ingest history
├── lessons.md               # curated standing rules from human feedback
├── feedback_log.md          # raw flagged corrections, unprocessed until distilled
├── lint-report.md            # overwritten each lint run
├── system/
├── firma/
├── produkty/
├── ceniky-a-kalkulace/
├── certifikace/
├── montaz-a-navody/
├── logistika/
├── marketing/
└── data-a-analyzy/
└── nastroje/
└── pravo-a-admin/
```

```python
VALID_CATEGORY = {
    "system", "firma", "produkty", "ceniky-a-kalkulace",
    "certifikace", "montaz-a-navody", "logistika", "marketing",
    "data-a-analyzy", "nastroje", "pravo-a-admin",
}
```

**A category folder is either flat or split — never assume which:**

- **Flat (2 layers):** `<category>/<slug>.md` files sit directly in the
  category folder. This is the default and stays the default as long as the
  category is small — most categories will likely never need anything else.
- **Split (3 layers):** once a category crosses the split threshold (see
  §1a), it gains topic subfolders: `<category>/<topic>/<slug>.md`, plus a
  `<category>/_index.md` domain index and one `<topic>/_index.md` per topic.

**How to tell which state a category is in:** check whether
`<category>/_index.md` exists. If it does, the category is split and that
file (not the root `index.md` section) is the authoritative list of what's
in it. If it doesn't, the category is flat and its entries live directly in
the root `index.md`. Same logic one level down for topics.

- `<slug>.md` is lowercase, hyphen-separated, derived from the page's
  subject (e.g. `verona-basalt-tile.md`). Once assigned, a slug is never
  renamed — if a product is discontinued or renamed, update the page content
  and add a redirect note (§4), don't rename the file.
- `_index.md` is a reserved filename — never used as a regular page slug.
- If a genuinely new top-level category is needed, that's a schema change —
  flag it rather than inventing a folder silently.

### 1a. Split trigger (deterministic, not an LLM judgment call)

A category or topic is flagged for splitting when it exceeds **both**:
- more than ~45 files, **and**
- an estimated total over ~3,000 tokens across those files' bodies.

This check is computed mechanically from `manifest.json` (see §9) — never
by an agent estimating it. When flagged, a human manually triggers the
split process (`POST /split/{category}`) — splitting is not automatic in
this MVP, matching the existing manual-trigger philosophy already used for
lint and distillation.

## 2. Page format (products & categories)

Every page starts with YAML frontmatter, then free-form markdown body.

```markdown
---
id: "products-verona-basalt-tile"
title: "Verona Basalt Tile"
layer: source                    # source | domain | topic | root
category: produkty               # required, from VALID_CATEGORY
doc_type: catalog                 # required, from VALID_DOC_TYPE
parent: "root"                    # id of the governing index (see §9)
access: public                    # required: public | internal | restricted
version: "2026-06"                # optional, human-readable label
valid_from: 2026-06-01            # required
valid_until: 2026-12-31           # optional — for docs that expire
last_updated: 2026-07-04           # set by agent/system, not copied from source
token_count: 842                   # set automatically after writing — do not set by hand
content_hash: "sha256:..."          # set automatically — hash of the raw source file
source_docs:                       # relative paths under raw/, for traceability
  - raw/catalogs/2026-outdoor-catalog.pdf
status: active                     # optional — only meaningful when category: products
tags: ["basalt", "outdoor"]        # optional, free-form
---

## Summary
One or two sentences — this is what gets pulled into the governing index.

## Details
Specs, pricing, dimensions, finishes. Prefer bullet lists and tables.

## Notes
Known issues, common questions, discontinued-product redirects, etc.
```

```python
VALID_DOC_TYPE = {
    "guide", "tech_sheet", "faq", "catalog", "policy", "certificate",
    "index",  # domain/topic index files — added for the layered structure
}
```

**System fields — set automatically, not by the writing agent:**
`id`, `layer`, `parent`, `token_count`, `content_hash`. The ingest agent
should leave these unset; a deterministic post-processing step fills them
in immediately after the page is written (see §9). This mirrors the design
principle that size/hash/hierarchy bookkeeping must be mechanical, not an
LLM judgment call — the agent's job is the content, nothing else.

**Everything else is unchanged from before:**
- `category` and `doc_type` are orthogonal.
- `access` is a hard filter, enforced by the query agent, not just metadata.
- `source_docs` is mandatory and traces back to the real source file.
- `valid_from`/`valid_until` determine current authority.
- All human-facing content (titles, body, index entries, summaries shown to
  a human operator) is written in **Czech**. Code-level values (category,
  doc_type, access, layer, file paths) stay as their fixed English enum
  values — that's the "programmatic stuff" that doesn't get translated.

## 3. File pairing

Every page is stored **alongside its raw source file**, same folder, same
basename — e.g. `products/verona-basalt-tile.md` +
`products/verona-basalt-tile.pdf`. This is handled automatically (not by
an agent): the backend saves the raw upload into the destination folder as
soon as the destination path is decided, before the writer agent runs.

- This is what lets a citation point to the actual original file for
  verification, and lets `wiki/` double as a normal browsable folder tree.
- Images: no OCR/vision pass — the page simply links to the image file.
- If a page is later updated from a different source format (e.g. was a
  `.docx`, now updated via `.pdf`), the old raw sibling is removed and
  replaced — a page only ever has one raw source paired to it at a time.

## 4. Discontinued / renamed products

Don't delete pages. Set `status: discontinued`, add a one-line redirect note
in Notes and in the governing index entry.

## 5. Ingestion flow (see also §8, §9)

1. A new file arrives (`/ingest`, or approval of a pending-review item).
2. **Hash check (deterministic, no LLM):** if the raw file's content hash
   already matches an entry in `manifest.json`, this exact file is already
   in the wiki — skip everything else and report "unchanged."
3. **Classification (LLM, read-only):** the classify agent proposes
   category / topic / doc_type / access / title / confidence /
   is-this-an-update. It does not write anything.
4. **Confidence gate (deterministic):**
   - `confidence: low` → the raw file and proposed classification are
     stored in a pending-review queue. Nothing is written to the wiki. A
     human approves or rejects it later (`/pending-review`). Silent
     misfiling is worse than a manual step at this scale — never guess past
     this gate.
   - `confidence: high` → proceed.
5. **Write (LLM):** the ingest agent writes the page content and updates
   the correct governing index entry — it no longer writes `log.md` itself.
6. **Finalize (deterministic, no LLM):** system frontmatter fields are
   computed and patched in; `manifest.json` is updated; the split-trigger
   check (§1a) runs and is reported if crossed; a structured `log.md`
   entry is appended (file, detected type, destination, confidence, or a
   failure message on error) — mechanical, same as the rest of this step.

## 6. Governing index format

One line per page, under a heading, inside whichever file currently
governs that category/topic (root `index.md`, `<category>/_index.md`, or
`<category>/<topic>/_index.md` — see §1). Never hand-edited.

```markdown
- [Verona Basalt Tile](products/verona-basalt-tile.md) — outdoor paving, active. Dark grey basalt, 60x60cm, from 1150 CZK/m².
```

The query agent always reads root `index.md` first, then follows links down
into `_index.md` files as needed (the 3-step traversal, §8) — it never
opens a page directly from the root index; it goes through whichever index
level currently governs it.

## 7. log.md, lessons.md, feedback_log.md, lint-report.md

- `log.md` — append-only, one structured entry per ingest run/outcome
  (status, file, detected type, destination, confidence, and a failure
  message when the run errors out). Written deterministically by the
  backend after each ingest/finalize step, not by the ingest agent — same
  "mechanical, not an LLM judgment call" principle as manifest.json and
  system frontmatter fields.
- `lessons.md` — curated, deduped rules; written only by the distill agent;
  read by every agent on every call.
- `feedback_log.md` — raw, append-only, written directly by the backend on
  thumbs-down; only the distill agent reads/marks entries processed.
- `lint-report.md` — overwritten in full each lint run.

## 8. Agent responsibilities

**Classify agent** (tools: `read_file`, `list_files`, `list_dirs`, `grep` —
read-only, proposes a destination via a structured `propose_classification`
call, never writes)
1. Read `lessons.md` and `index.md` for context.
2. Check whether the target category is already split (`list_dirs`) and,
   if so, whether the document fits an existing topic — never invents a
   new topic.
3. Check whether this updates an existing page.
4. Call `propose_classification` exactly once, including a confidence
   level. Default to `low` whenever unsure.

**Ingest agent (writer)** (tools: `read_file`, `list_files`, `list_dirs`,
`grep`, `write_file` — write access)
1. Given an already-decided classification and an exact destination path,
   write the page (content only — system fields are filled in afterward).
2. Update the governing index entry (told explicitly which file to update).

The `log.md` entry is no longer this agent's job — it's appended
deterministically by the backend during finalize (§5, §9).

**Query agent** (tools: `read_file`, `list_files`, `grep` — read-only)
1. Read `lessons.md` and root `index.md`.
2. **3-step traversal:** decide which category/topic indices are relevant
   → open those (`_index.md` files, following links from the root) → read
   only the 2-4 most relevant source pages.
3. `access: public` filter enforced when `mode="public"` (customer email
   drafts); `access: restricted` surfaced with a sign-off note for internal
   queries.
4. Check `valid_until`; flag stale pages instead of citing as current.
5. Answer, citing page paths.

**Distill agent** (tools: `read_file`, `write_file` — restricted to
`lessons.md`, `feedback_log.md`, and page factual corrections) — unchanged
responsibilities. Note: since a factual correction changes a page's body
directly, `token_count` may go stale until the next deterministic refresh
pass (run automatically after `/distill`).

**Lint agent** (tools: `read_file`, `list_files`, `grep`, `write_file` —
restricted to `lint-report.md`)
Same five checks as before (orphan pages, broken references, stale claims,
missing provenance, contradictions), plus a sixth:

6. **TOKEN BUDGET** — categories/topics flagged by the deterministic
   split-trigger check (§1a, precomputed and handed to the agent — it does
   not calculate this itself). Report them; don't split them.

**Split agent** (tools: `read_file`, `list_files`, `list_dirs`,
`write_file`, `move_file` — manually triggered via `POST /split/{category}`,
never automatic)
1. Read every page in the flagged category.
2. Propose 2-5 topic groupings (lowercase-hyphen slugs).
3. Move each page (and its paired raw source) into its topic subfolder.
4. Create a `_index.md` per topic and a `_index.md` for the category,
   replacing the flat page list with short topic abstracts.
5. Update root `index.md`'s section for that category down to a short
   category abstract + link.

## 9. manifest.json

Not an agent-facing file — no agent reads or writes it directly (it's
maintained by deterministic Python code, not exposed as a tool). Tracks,
per page path: `id`, `layer`, `category`, `topic`, `parent`, `token_count`,
`content_hash`, `title`. Used for: fast hash-based duplicate detection on
ingest, fast split-trigger checks without re-reading every file body, and
manifest → path lookups.

## 10. Pending-review queue

Not part of `wiki/` — lives in a separate `pending_review/` folder at the
project root. Each queued item is a raw file plus a small JSON sidecar
(`{id}.json`) recording the proposed classification and reasoning. Approving
an item runs it through the same write/finalize steps as a normal
high-confidence ingest; rejecting deletes both files. Nothing in the queue
is ever included in query-agent traversal — it isn't part of the wiki until
approved.

## 11. Deletion

`DELETE /wiki/file` removes a page and its paired raw source. By default it
archives them to `archive/{timestamp}/...` rather than destroying them
outright, and deterministically strips any now-dead reference to that path
from every index file in the tree (root and any `_index.md` files) — no LLM
involved in that cleanup step.

## 12. Open conventions (fill in as the project evolves)

- Tone/style guide for email replies.
- Per-category retention policy for archived versions (currently: archive
  everything, everywhere, by default).
- What counts as "relevant enough" to include in an email answer vs.
  deferring to a human.
