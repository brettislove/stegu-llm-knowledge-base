# Knowledge Base MVP — backend

Three agents (ingest / query / distill) sharing one wiki of markdown pages,
per `SCHEMA.md`. No vector DB — the whole wiki fits in an `index.md` scan
plus a handful of targeted `read_file` calls, per Karpathy's llm-wiki idea.

## Setup

```bash
cd kb-mvp
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in ANTHROPIC_API_KEY
```

## Run

From the project root (important — imports assume `backend` is a package
rooted here):

```bash
uvicorn backend.main:app --reload --port 8000
```

## Try it

**Ingest a document** — either a raw PDF (Claude reads it natively, no
conversion step) or already-converted markdown:

```bash
# PDF
python3 -c "
import base64, json
with open('some-catalog.pdf', 'rb') as f:
    data = base64.b64encode(f.read()).decode()
print(json.dumps({'filename': 'some-catalog.pdf', 'pdf_base64': data}))
" > /tmp/ingest_payload.json

curl -X POST http://localhost:8000/ingest \
  -H "Content-Type: application/json" \
  -d @/tmp/ingest_payload.json

# Already-converted markdown
curl -X POST http://localhost:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "filename": "verona-basalt.md",
    "markdown": "# Verona Basalt Tile\n\nDark grey basalt paving tile, 60x60cm.\nPrice: 1150 CZK/m^2."
  }'
```

Check what it did:

```bash
curl http://localhost:8000/wiki/files
curl "http://localhost:8000/wiki/file?path=index.md"
```

**Ask a question from internal docs** (internal/dashboard mode):

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question": "What outdoor paving products do we have and what do they cost?", "mode": "internal"}'
```

**Ask a question from public docs** (public-only filtering):

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question": "A customer is asking about the Verona Basalt tile price.", "mode": "public"}'
```

**Flag a bad answer** (instant, no agent call):

```bash
curl -X POST http://localhost:8000/feedback \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What is the price of the Verona Basalt tile?",
    "bad_answer": "45 EUR/m2",
    "correction": "Prices are always in CZK. Should be 1150 CZK/m2."
  }'
```

**Run distillation** (processes feedback into lessons.md / page corrections):

```bash
curl -X POST http://localhost:8000/distill
```

## Dashboard (frontend)

```bash
cd frontend
npm install
cp .env.example .env   # only needed if backend isn't on localhost:8000
npm run dev
```

Opens at `http://localhost:5173`. Three tabs:
- **Ask** — chat against the wiki, toggle between `internal` (staff) and
  `public` (public-only) modes. Cited pages show up on the right as
  stamped index cards (PUBLIC / INTERNAL / RESTRICTED). Any answer can be
  flagged with a one-line correction, which goes straight to `/feedback`.
- **Ingest** — drop a PDF or a `.md` file. PDFs are sent to `/ingest` as
  base64 and Claude reads them natively; markdown files are sent as plain
  text. Both update the wiki the same way.
- **Review feedback** — shows `feedback_log.md` and `lessons.md` as-is, with
  a button to run `/distill`.

The left rail doubles as a card-catalog browser — click a category to list
its pages, click a page to view its raw content (with its access stamp) in
a modal.

## What's not built yet

- Automatic triggering of `/distill` (currently a manual button — fine for MVP).
- Streaming responses (chat currently waits for the full agent loop to finish
  before showing an answer — fine while the wiki is small, worth revisiting
  if ingest/query turns start taking a while).

## Project layout

```
kb-mvp/
├── SCHEMA.md              # wiki conventions — read by every agent
├── wiki/                  # the knowledge base itself
├── raw/                   # original PDFs
├── backend/
│   ├── config.py          # paths + fixed vocabularies (VALID_CATEGORY etc.)
│   ├── agentic_loop.py     # shared Claude tool-use loop
│   ├── tools/
│   │   ├── file_tools.py   # sandboxed read/write/list/grep implementations
│   │   └── tool_defs.py    # Claude tool schemas per agent
│   ├── agents/
│   │   ├── ingest_agent.py
│   │   ├── query_agent.py
│   │   └── distill_agent.py
│   └── main.py             # FastAPI endpoints
└── frontend/
    └── src/
        ├── api.js                       # fetch wrapper for the backend
        ├── App.jsx
        └── components/
            ├── Sidebar.jsx               # tab nav + category/file browser
            ├── ChatPanel.jsx             # Ask tab
            ├── IngestPanel.jsx           # Ingest tab
            ├── ReviewPanel.jsx           # Review feedback tab
            ├── CitedPagesPanel.jsx       # right rail, stamped index cards
            ├── FileViewerModal.jsx       # raw page viewer
            └── AccessStamp.jsx           # the PUBLIC/INTERNAL/RESTRICTED stamp
```
