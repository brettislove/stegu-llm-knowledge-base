# LLM Knowledge Base

An internal knowledge base and Q&A assistant built for a real construction-materials e-shop, so staff (and eventually customers) can ask natural-language questions against the company's actual product catalog, pricing, certifications, and policies — with every answer traceable back to a source document.

Built and deployed for a real client; currently in active use.

## Why no vector database

Most RAG systems reach for embeddings + a vector store. This one doesn't, following Andrej Karpathy's "llm-wiki" idea: at this scale (fewer than ~200 documents), the entire knowledge base fits in an `index.md` scan plus a handful of targeted file reads. Claude agents navigate a plain hierarchy of markdown files via tool calls (`read_file`, `list_files`, `grep`) instead of similarity search over embeddings — simpler to reason about, easier to audit, and every answer can cite the exact page it came from.

The full convention for how the wiki is structured, and how each agent is allowed to read/write it, is documented in [`SCHEMA.md`](SCHEMA.md).

## How it works

1. **Ingest** — a document (PDF, DOCX, XLSX, or already-converted markdown) comes in via the API or the dashboard's Ingest tab.
2. **Classify** (LLM, read-only) — an agent proposes a category, doc type, access level, and confidence score. Low confidence → the document is queued in `pending_review/` for a human to approve or reject; nothing is written to the wiki yet.
3. **Write** (LLM) — on high confidence (or human approval), an agent writes the page and updates the relevant index.
4. **Finalize** (deterministic, no LLM) — hashing, token counts, and `manifest.json`/`log.md` bookkeeping happen in code, not by the model.
5. **Query** — a separate agent answers questions by reading `index.md`, following links into the relevant section, then reading only the 2–4 most relevant source pages. Access control (`public` / `internal` / `restricted`) is enforced per query mode.
6. **Feedback → distill** — a thumbs-down on an answer is logged; a distill agent periodically turns accumulated feedback into corrections and standing rules (`lessons.md`), which every agent reads on every call.
7. **Lint / split** — a lint agent checks for orphan pages, broken references, and stale claims; a split agent (human-triggered) reorganizes a category into subtopics once it crosses a size threshold.

## Architecture

- **Backend** — FastAPI (Python). Claude agents for classify / ingest / query / distill / lint / split, each with a narrow, explicit tool set (see `SCHEMA.md` §8).
- **Storage** — the wiki, raw source files, and the pending-review queue live in the client's own Microsoft OneDrive, accessed via the Microsoft Graph API (app-only, `Files.ReadWrite.All`) rather than local disk. This was a contractual requirement — the client's business data stays in their own Microsoft 365 tenant, not on a third-party server's filesystem.
- **Auth** — Clerk. The frontend signs users in with Clerk; the backend verifies the resulting session JWT against Clerk's public JWKS on every request (`backend/auth.py`), applied as a single middleware rather than per-route checks.
- **Frontend** — React + Vite. Three tabs: **Ask** (chat against the wiki, with cited pages shown as access-stamped cards, and inline answer correction), **Ingest** (drop a PDF or markdown file), **Review feedback** (see flagged corrections and trigger distillation). A left-rail card-catalog view browses the wiki directly.

## API

| Endpoint | Purpose |
|---|---|
| `POST /ingest`, `POST /ingest/stream` | Submit a document for classification and (if confident) writing |
| `GET /pending-review`, `POST /pending-review/{id}/approve`, `POST /pending-review/{id}/reject` | Human review queue for low-confidence ingests |
| `POST /query` | Ask a question (`mode: "internal"` or `"public"`) |
| `POST /feedback` | Flag an answer with a correction |
| `POST /distill` | Turn accumulated feedback into lessons/corrections |
| `POST /lint` | Run consistency checks over the wiki |
| `POST /split/{category}` | Reorganize an overgrown category into subtopics |
| `GET /wiki/files`, `GET /wiki/file`, `DELETE /wiki/file` | Browse / read / remove wiki pages |
| `GET /wiki/manifest`, `GET /spend`, `GET /health` | Bookkeeping, usage/cost telemetry, health check |

## Running this yourself

This isn't a casual clone-and-run project — the backend is hardwired (by design) to a real Microsoft 365 tenant and a real Clerk project, and won't even start without them (`backend/config.py` reads required env vars directly, no fallback). To actually run it you'd need:

- An Azure AD app registration with `Files.ReadWrite.All` (application permission, admin-consented) against the target OneDrive
- A Clerk application (for both the frontend publishable key and the backend's JWKS URL)
- An Anthropic API key

### Backend environment variables

```
ANTHROPIC_API_KEY=...
CLAUDE_MODEL=claude-sonnet-5          # optional, this is the default
GRAPH_TENANT_ID=...
GRAPH_CLIENT_ID=...
GRAPH_CLIENT_SECRET=...
GRAPH_DRIVE_USER=...                   # UPN of the OneDrive owner
ONEDRIVE_PROJECT_ROOT=STEGU_WIKI       # optional, this is the default
CLERK_JWKS_URL=...
ALLOWED_ORIGINS=http://localhost:5173  # comma-separated, for CORS
CZK_PER_USD=21.5                       # optional, for the cost dashboard
```

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn backend.main:app --reload --port 8000
```

### Frontend environment variables

```
VITE_API_URL=http://localhost:8000
VITE_CLERK_PUBLISHABLE_KEY=...
```

```bash
cd frontend
npm install
npm run dev
```

Deployed in production as a FastAPI service (Render) behind a static Vercel-hosted frontend.

## Project layout

```
.
├── SCHEMA.md              # wiki conventions — read by every agent on every call
├── CLAUDE.md              # pointer to SCHEMA.md for agent instruction files
├── TODO.md                # deliberately deferred engineering items, with reasoning
├── wiki/                  # sample of the knowledge base itself (see note below)
├── raw/, pending_review/, archive/   # same — see note below
├── backend/
│   ├── config.py           # env-driven config, Graph client wiring
│   ├── auth.py              # Clerk session verification middleware
│   ├── graph_client.py      # Microsoft Graph API wrapper
│   ├── converters.py        # PDF/DOCX/XLSX → markdown
│   ├── agentic_loop.py       # shared Claude tool-use loop
│   ├── tools/                # sandboxed file read/write/list/grep, spend tracking
│   ├── agents/                # classify / ingest / query / distill / lint / split
│   └── main.py                 # FastAPI endpoints
└── frontend/
    └── src/
        ├── api.js
        ├── App.jsx
        └── components/          # Sidebar, ChatPanel, IngestPanel, ReviewPanel, ...
```

**Note on `wiki/`, `raw/`, `pending_review/`, `archive/`:** these folders are committed as a point-in-time sample from an earlier phase of the project, before storage moved to OneDrive/Graph (see `SCHEMA.md`'s runtime note). The live system reads and writes these paths in the client's OneDrive, not from this repository — the committed copies are frozen and won't reflect the current live state.

## What's not built yet

- Automatic triggering of `/distill` (currently a manual button — fine at this scale).
- Streaming responses for `/query` (currently waits for the full agent loop).
- See [`TODO.md`](TODO.md) for deferred backend-engineering items and the reasoning behind deferring each one.
