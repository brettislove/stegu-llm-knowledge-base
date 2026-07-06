# SCHEMA.md — Knowledge Base Conventions

This document defines how the wiki is structured and how agents (ingest, query,
distill) are expected to read and write it. All agents receive this file as
part of their system context on every call.

## 1. Directory layout

Top-level folders mirror `VALID_CATEGORY` exactly — one folder per document
domain, not per "product vs. category" as in earlier drafts:

```
wiki/
├── index.md              # catalog — one entry per page, kept short
├── log.md                # append-only ingest history (facts: what changed, when)
├── lessons.md            # curated standing rules from human feedback
├── feedback_log.md       # raw flagged corrections, unprocessed until distilled
├── installation/
├── chemistry/
├── products/
├── complaints/
├── logistics/
├── business/
├── general/
├── pricing/
└── internal_process/
```

```python
VALID_CATEGORY = {
    "installation", "chemistry", "products", "complaints",
    "logistics", "business", "general", "pricing", "internal_process",
}
```

- `<slug>.md` files live directly inside their category folder, no further
  nesting. `<slug>` is lowercase, hyphen-separated, derived from the page's
  subject (e.g. `verona-basalt-tile.md`). Once assigned, a slug is never
  renamed — if a product is discontinued or renamed, update the page content
  and add a redirect note (see §4), don't rename the file.
- The distinction between e.g. "a specific product" and "a product family
  overview" lives in `doc_type` (§2), not in the folder structure.
- If a genuinely new top-level category is needed, that's a schema change —
  flag it rather than inventing a folder silently, and add it to
  `VALID_CATEGORY` in the ingestion code as well as here.

## 2. Page format (products & categories)

Every page starts with YAML frontmatter, then free-form markdown body.

```markdown
---
title: "Verona Basalt Tile"
category: products              # required, from VALID_CATEGORY
doc_type: catalog                # required, from VALID_DOC_TYPE
access: public                   # required: public | internal | restricted
version: "2026-06"               # optional, human-readable label
valid_from: 2026-06-01           # required
valid_until: 2026-12-31          # optional — for docs that expire (certificates, price lists)
last_updated: 2026-07-04         # set by agent, not copied from source
source_docs:                     # relative paths under raw/, for traceability
  - raw/catalogs/2026-outdoor-catalog.pdf
status: active                   # optional — only meaningful when category: products
                                  # active | discontinued | seasonal
---

## Summary
One or two sentences — this is what gets pulled into index.md.

## Details
Specs, pricing, dimensions, finishes, whatever is relevant. Prefer bullet
lists and tables over prose paragraphs — easier for the query agent to
extract precisely.

## Notes
Anything that doesn't fit above: known issues, common customer questions,
discontinued-product redirects, etc.
```

```python
VALID_DOC_TYPE = {
    "guide", "tech_sheet", "faq", "catalog", "policy", "certificate",
}
```

Rules:
- **Frontmatter fields are fixed.** Don't add ad hoc keys per page — if a new
  field is genuinely needed across many pages, that's a schema change, add it
  here first.
- **`category` and `doc_type` are orthogonal.** `category` is the document's
  domain (what it's about), `doc_type` is its form (what kind of document it
  is). E.g. `chemistry` + `certificate`, `products` + `catalog`,
  `installation` + `guide` are all valid combinations.
- **`access` is a hard filter, not just metadata.** The query agent, when
  drafting a customer-facing email reply, may only cite `public` pages.
  `internal` and `restricted` pages are available to internal/dashboard
  queries only — `restricted` additionally implies the page shouldn't be
  quoted verbatim even internally without a human sign-off.
- **`source_docs` is mandatory** and is how answers get traced back to a real
  PDF. Every fact on a page should be attributable to at least one doc in this
  list.
- **`valid_from`/`valid_until`** determine whether a page is currently
  authoritative. The query agent should treat a page past its `valid_until`
  as stale and flag it rather than cite it as current.
- **`last_updated` is set by the agent**, not copied from the source PDF.

## 3. index.md format

One line per page, generated/maintained by the ingest agent — never hand-edited.

```markdown
# Index

## Products
- [Verona Basalt Tile](products/verona-basalt-tile.md) — outdoor paving, active. Dark grey basalt, 60x60cm, from 1150 CZK/m².
- [Verona Slate Tile](products/verona-slate-tile.md) — outdoor paving, DISCONTINUED, see Verona Basalt.

## Categories
- [Outdoor Paving](categories/outdoor-paving.md) — all outdoor tile products.
```

The query agent reads this file **first, always**, before opening any
individual page. Keep each line short enough that the whole index stays cheap
to read even as the catalog grows toward ~200 pages.

## 4. Discontinued / renamed products

Don't delete pages. Set `status: discontinued`, add a one-line redirect note
in the page's Notes section and in its index.md entry (see example above). The
query agent should surface the redirect rather than silently answering as if
the product still exists.

## 5. log.md format

Append-only, one entry per ingest run. Never edited or reordered.

```markdown
## 2026-07-04 — ingested 2026-outdoor-catalog.pdf
- Created: products/verona-basalt-tile.md
- Updated: products/verona-slate-tile.md (marked discontinued)
- Updated: categories/outdoor-paving.md (added new entry)
```

## 6. lessons.md format

Curated, deduplicated, human-readable rules distilled from feedback. Read by
**both** ingest and query agents on every call — a lesson can affect how
future documents get ingested, not just how questions get answered.

```markdown
# Lessons

## Pricing & content
- Always quote prices in CZK, never EUR.
- "Verona Slate" is discontinued — redirect to "Verona Basalt".

## Tone & format
- Keep email replies under ~150 words unless the customer asks for full specs.
- Never promise delivery dates more precise than "2–3 weeks" without an explicit order reference.
```

Only the **distill agent** writes to this file. It must dedupe against
existing lessons rather than appending near-duplicates — if a new correction
overlaps an existing lesson, it edits/tightens that lesson instead of adding a
new line.

## 7. feedback_log.md format

Raw, append-only, written directly by the backend on thumbs-down (no agent
call). Only the distill agent reads and marks entries processed.

```markdown
## 2026-07-04 14:32 — status: unprocessed
Q: "What's the price of the Verona Slate tile?"
Bad answer: "€45/m²"
Correction: "Prices are always in CZK. Should be 1150 CZK/m². Also Verona Slate is discontinued."
```

After distillation, the backend (not the agent) flips `status: unprocessed`
to `status: processed` — keeps the distill agent from re-processing on every
run.

## 7.5 lint-report.md format

Overwritten in full on every lint run — NOT append-only, unlike log.md and
feedback_log.md. Only the lint agent writes here, and only here (see §8).

```markdown
# Lint Report — 2026-07-06

## Orphan pages
- No issues found.

## Broken references
- index.md links to products/verona-slate-tile.md, which is discontinued
  but still present — not actually broken, listed for awareness.

## Stale claims
- pricing/2026-06-price-list.md has valid_until: 2026-06-30, which has
  passed. Consider re-ingesting a current price list.

## Missing provenance
- No issues found.

## Contradictions
- No issues found.
```

## 8. Agent responsibilities

**Ingest agent** (tools: `read_file`, `write_file`, `list_files`)
1. Read `lessons.md` and `index.md` for context.
2. Read the new source markdown (converted from PDF).
3. Decide: new page, or update to an existing page? (check index.md first)
4. Write/update the page(s) following §2.
5. Update `index.md` (§3).
6. Append an entry to `log.md` (§5).

**Query agent** (tools: `read_file`, `list_files`, `grep` — read-only, no
write access)
1. Read `lessons.md` and `index.md`.
2. Pick the 2–4 most relevant pages, read them.
3. **If drafting a customer-facing email reply**, filter to `access: public`
   pages only — never cite `internal` or `restricted` pages in that context.
   Internal/dashboard queries may read `internal` pages, but `restricted`
   pages should still surface with a note that human sign-off is needed
   before quoting them.
4. Check `valid_until` on any page used — if a page is past its validity date,
   flag it as potentially stale instead of citing it as current fact.
5. Answer, citing which page(s) the answer came from.
6. If the answer touches a discontinued/redirected product, say so explicitly.

**Distill agent** (tools: `read_file`, `write_file` — only on `lessons.md`,
`feedback_log.md`, and product/category pages if a factual correction)
1. Read unprocessed entries in `feedback_log.md`.
2. Classify each: factual/content error vs. behavioral rule.
3. Factual → correct the relevant page directly (update `last_updated`).
4. Behavioral → merge into `lessons.md`, deduping.
5. Signal which entries are processed (backend flips the status flag).

**Lint agent** (tools: `read_file`, `list_files`, `grep`, `write_file` —
write access restricted to `lint-report.md` only, enforced in code, not just
by prompt)
1. Compare `index.md` against actual files on disk to find orphans/broken
   references.
2. Check frontmatter completeness and `valid_until` staleness per page.
3. Look for cross-page contradictions on the same subject.
4. Write the full report to `lint-report.md` (overwrite, not append).
5. Fix nothing — report only. A human decides what to act on, likely via a
   normal ingest/distill run or a manual edit.

## 9. Open conventions (fill in as the project evolves)

- Tone/style guide for email replies (formal? friendly? company-specific phrasing?)
- Language(s) supported
- What counts as "relevant enough" to include in an email answer vs. deferring to a human