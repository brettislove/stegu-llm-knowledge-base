"""
FastAPI backend for the knowledge base MVP — local/test version of the
layered-index design (see SCHEMA.md and the Design Notes). Runs entirely
against local disk (wiki/, pending_review/, archive/) — no OneDrive/Graph
API, that's the production-target design, not this environment.

Run from the project root with:
    uvicorn backend.main:app --reload --port 8000
"""
import asyncio
import base64
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.agents.classify_agent import classify_document
from backend.agents.ingest_agent import write_page
from backend.agents.query_agent import answer_query
from backend.agents.distill_agent import run_distillation
from backend.agents.lint_agent import run_lint
from backend.agents.split_agent import split_category
from backend.tools import file_tools, hashing
from backend.tools.postprocess import finalize_page, refresh_token_counts
from backend.converters import convert_file
from backend.config import PENDING_REVIEW_ROOT, WIKI_ROOT, VALID_CATEGORY

app = FastAPI(title="Knowledge Base MVP")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # fine for local MVP testing; tighten before any real deployment
    allow_methods=["*"],
    allow_headers=["*"],
)

# Single-writer discipline (Design Notes §6.1), adapted for a single local
# process: one asyncio.Lock instead of a cloud lock file — avoids two
# concurrent uploads racing to edit the same index file.
_ingest_lock = asyncio.Lock()


class IngestRequest(BaseModel):
    filename: str
    file_base64: str


class QueryRequest(BaseModel):
    question: str
    mode: str = "internal"


class FeedbackRequest(BaseModel):
    question: str
    bad_answer: str
    correction: str


class ReviewDecisionOverride(BaseModel):
    category: Optional[str] = None
    topic: Optional[str] = None
    doc_type: Optional[str] = None
    title: Optional[str] = None
    access: Optional[str] = None


def _resolve_destination(classification: dict) -> str:
    is_update_to = classification.get("is_update_to") or ""
    if is_update_to:
        return is_update_to
    category = classification["category"]
    topic = classification.get("topic") or ""
    slug = file_tools.slugify(classification["title"])
    prefix = f"{category}/{topic}/" if topic else f"{category}/"
    return f"{prefix}{slug}.md"


def _store_raw_sibling(destination_path: str, filename: str, raw_bytes: bytes) -> None:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    dest_dir = (WIKI_ROOT / destination_path).parent
    dest_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(destination_path).stem
    # Remove any stale raw sibling with a different extension (e.g. this
    # update switched source format from .docx to .pdf).
    for sibling in dest_dir.glob(f"{stem}.*"):
        if sibling.suffix != ".md":
            sibling.unlink()
    (dest_dir / f"{stem}.{ext}").write_bytes(raw_bytes)


def _build_llm_content(filename: str, file_base64: str, raw_bytes: bytes):
    if filename.lower().endswith(".pdf"):
        return [{
            "type": "document",
            "source": {"type": "base64", "media_type": "application/pdf", "data": file_base64},
        }]
    _, markdown = convert_file(filename, file_base64)
    return markdown


def _run_full_ingest(filename: str, raw_bytes: bytes, classification: dict) -> dict:
    """High-confidence path: write the page, pair the raw source, finalize
    system frontmatter + manifest, check the split trigger."""
    file_base64 = base64.b64encode(raw_bytes).decode()
    content_for_llm = _build_llm_content(filename, file_base64, raw_bytes)

    destination_path = _resolve_destination(classification)
    category = classification["category"]
    topic = classification.get("topic") or None
    governing_index = file_tools.governing_index_path(category, topic)

    _store_raw_sibling(destination_path, filename, raw_bytes)

    result = write_page(filename, content_for_llm, destination_path, governing_index, classification)

    raw_hash = hashing.compute_hash_bytes(raw_bytes)
    finalize_page(destination_path, category, topic, raw_hash)

    split_hint = None
    prefix = f"{category}/{topic}" if topic else category
    if hashing.needs_split(prefix):
        split_hint = (
            f"Category '{prefix}' has crossed the file-count/token threshold — "
            f"consider running POST /split/{category}."
        )

    return {
        "status": "ingested",
        "destination": destination_path,
        "summary": result["final_text"],
        "turns": result["turns"],
        "cache_read_tokens": result.get("cache_read_tokens", 0),
        "split_hint": split_hint,
    }


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _write_and_finalize(filename, raw_bytes, classification, content_for_llm):
    destination_path = _resolve_destination(classification)
    category = classification["category"]
    topic = classification.get("topic") or None
    governing_index = file_tools.governing_index_path(category, topic)

    _store_raw_sibling(destination_path, filename, raw_bytes)
    result = write_page(
        filename, content_for_llm, destination_path, governing_index, classification
    )
    return destination_path, category, topic, result


def _finalize(destination_path, category, topic, raw_bytes, result):
    raw_hash = hashing.compute_hash_bytes(raw_bytes)
    finalize_page(destination_path, category, topic, raw_hash)

    split_hint = None
    prefix = f"{category}/{topic}" if topic else category
    if hashing.needs_split(prefix):
        split_hint = (
            f"Category '{prefix}' has crossed the file-count/token threshold — "
            f"consider running POST /split/{category}."
        )
    return {
        "status": "ingested",
        "destination": destination_path,
        "summary": result["final_text"],
        "turns": result["turns"],
        "cache_read_tokens": result.get("cache_read_tokens", 0),
        "split_hint": split_hint,
    }


def _ingest_pipeline(req: IngestRequest):
    """
    Sync generator yielding one SSE 'data: {...}' string per stage
    transition. Mirrors the exact same logic as /ingest, just narrated
    stage-by-stage instead of returning a single JSON blob at the end.
    """
    yield _sse({"stage": "upload", "status": "start", "label": "Nahrávání souboru"})
    try:
        raw_bytes = base64.b64decode(req.file_base64)
    except Exception as e:
        yield _sse(
            {"stage": "upload", "status": "error", "message": f"Malformed base64: {e}"}
        )
        return
    yield _sse({"stage": "upload", "status": "done"})

    yield _sse(
        {"stage": "hash_check", "status": "start", "label": "Kontrola duplicity"}
    )
    raw_hash = hashing.compute_hash_bytes(raw_bytes)
    existing = hashing.find_by_hash(raw_hash)
    if existing:
        yield _sse({"stage": "hash_check", "status": "done"})
        yield _sse(
            {
                "stage": "finished",
                "result": {
                    "status": "unchanged",
                    "message": f"Tento soubor je již ve wiki beze změny ({existing}).",
                },
            }
        )
        return
    yield _sse({"stage": "hash_check", "status": "done"})

    yield _sse({"stage": "convert", "status": "start", "label": "Převod dokumentu"})
    try:
        content_for_llm = _build_llm_content(req.filename, req.file_base64, raw_bytes)
    except ValueError as e:
        yield _sse({"stage": "convert", "status": "error", "message": str(e)})
        return
    yield _sse({"stage": "convert", "status": "done"})

    yield _sse(
        {"stage": "classify", "status": "start", "label": "Klasifikace dokumentu"}
    )
    try:
        classification = classify_document(req.filename, content_for_llm)
    except Exception as e:
        yield _sse({"stage": "classify", "status": "error", "message": str(e)})
        return
    yield _sse(
        {
            "stage": "classify",
            "status": "done",
            "detail": {
                "category": classification.get("category"),
                "topic": classification.get("topic"),
                "confidence": classification.get("confidence"),
            },
        }
    )

    if classification.get("confidence") == "low":
        qid = uuid.uuid4().hex[:12]
        ext = req.filename.rsplit(".", 1)[-1] if "." in req.filename else "bin"
        PENDING_REVIEW_ROOT.mkdir(parents=True, exist_ok=True)
        (PENDING_REVIEW_ROOT / f"{qid}.{ext}").write_bytes(raw_bytes)
        meta = {
            "filename": req.filename,
            "classification": classification,
            "queued_at": datetime.now(timezone.utc).isoformat(),
            "ext": ext,
        }
        (PENDING_REVIEW_ROOT / f"{qid}.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        yield _sse(
            {
                "stage": "finished",
                "result": {
                    "status": "pending_review",
                    "queue_id": qid,
                    "reasoning": classification.get("reasoning", ""),
                    "proposed": classification,
                    "message": "Low classification confidence — queued for human review.",
                },
            }
        )
        return

    yield _sse({"stage": "write", "status": "start", "label": "Zápis stránky do wiki"})
    try:
        destination_path, category, topic, agent_result = _write_and_finalize(
            req.filename, raw_bytes, classification, content_for_llm
        )
    except Exception as e:
        yield _sse({"stage": "write", "status": "error", "message": str(e)})
        return
    yield _sse({"stage": "write", "status": "done"})

    yield _sse(
        {
            "stage": "finalize",
            "status": "start",
            "label": "Dokončování (hash, token count, manifest)",
        }
    )
    try:
        result = _finalize(destination_path, category, topic, raw_bytes, agent_result)
    except Exception as e:
        yield _sse({"stage": "finalize", "status": "error", "message": str(e)})
        return
    yield _sse({"stage": "finalize", "status": "done"})

    yield _sse({"stage": "finished", "result": result})


@app.post("/ingest")
async def ingest(req: IngestRequest):
    async with _ingest_lock:
        try:
            raw_bytes = base64.b64decode(req.file_base64)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Malformed base64: {e}")

        # Deterministic hash check — no LLM call at all if this exact file
        # is already in the wiki.
        raw_hash = hashing.compute_hash_bytes(raw_bytes)
        existing = hashing.find_by_hash(raw_hash)
        if existing:
            return {
                "status": "unchanged",
                "message": f"Tento soubor je již ve wiki beze změny ({existing}).",
            }

        try:
            content_for_llm = _build_llm_content(req.filename, req.file_base64, raw_bytes)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        try:
            classification = classify_document(req.filename, content_for_llm)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Classification failed: {e}")

        if classification.get("confidence") == "low":
            qid = uuid.uuid4().hex[:12]
            ext = req.filename.rsplit(".", 1)[-1] if "." in req.filename else "bin"
            PENDING_REVIEW_ROOT.mkdir(parents=True, exist_ok=True)
            (PENDING_REVIEW_ROOT / f"{qid}.{ext}").write_bytes(raw_bytes)
            meta = {
                "filename": req.filename,
                "classification": classification,
                "queued_at": datetime.now(timezone.utc).isoformat(),
                "ext": ext,
            }
            (PENDING_REVIEW_ROOT / f"{qid}.json").write_text(
                json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return {
                "status": "pending_review",
                "queue_id": qid,
                "reasoning": classification.get("reasoning", ""),
                "proposed": classification,
                "message": "Low classification confidence — queued for human review (GET /pending-review).",
            }

        try:
            return _run_full_ingest(req.filename, raw_bytes, classification)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))


@app.post("/ingest/stream")
async def ingest_stream(req: IngestRequest):
    async def gen():
        await _ingest_lock.acquire()
        try:
            for chunk in _ingest_pipeline(req):
                yield chunk
        finally:
            _ingest_lock.release()

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/pending-review")
def list_pending_review():
    items = []
    if PENDING_REVIEW_ROOT.exists():
        for meta_path in sorted(PENDING_REVIEW_ROOT.glob("*.json")):
            items.append({"id": meta_path.stem, **json.loads(meta_path.read_text(encoding="utf-8"))})
    return {"items": items}


@app.post("/pending-review/{queue_id}/approve")
async def approve_pending_review(queue_id: str, override: ReviewDecisionOverride = ReviewDecisionOverride()):
    meta_path = PENDING_REVIEW_ROOT / f"{queue_id}.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Unknown pending-review item.")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    classification = meta["classification"]
    for key, value in override.model_dump(exclude_none=True).items():
        classification[key] = value
    classification["confidence"] = "high"  # a human approved it

    raw_path = PENDING_REVIEW_ROOT / f"{queue_id}.{meta['ext']}"
    if not raw_path.exists():
        raise HTTPException(status_code=404, detail="Queued raw file missing.")
    raw_bytes = raw_path.read_bytes()

    async with _ingest_lock:
        try:
            content_for_llm = _build_llm_content(meta["filename"], base64.b64encode(raw_bytes).decode(), raw_bytes)
            destination_path, category, topic, agent_result = _write_and_finalize(
                meta["filename"], raw_bytes, classification, content_for_llm
            )
            result = _finalize(destination_path, category, topic, raw_bytes, agent_result)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    raw_path.unlink(missing_ok=True)
    meta_path.unlink(missing_ok=True)
    return result


@app.post("/pending-review/{queue_id}/reject")
def reject_pending_review(queue_id: str):
    meta_path = PENDING_REVIEW_ROOT / f"{queue_id}.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Unknown pending-review item.")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    (PENDING_REVIEW_ROOT / f"{queue_id}.{meta['ext']}").unlink(missing_ok=True)
    meta_path.unlink()
    return {"status": "rejected"}


@app.delete("/wiki/file")
def delete_wiki_file(path: str, archive: bool = True):
    try:
        message = file_tools.delete_file(path, archive=archive)
        hashing.remove_entry(path)
        return {"status": "deleted", "message": message}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/split/{category}")
async def split(category: str):
    if category not in VALID_CATEGORY:
        raise HTTPException(status_code=400, detail=f"Unknown category: {category}")
    async with _ingest_lock:  # split rewrites the same index files ingestion touches
        try:
            result = split_category(category)
            return {"summary": result["final_text"], "turns": result["turns"]}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))


@app.get("/wiki/manifest")
def get_manifest():
    return hashing.load_manifest()


@app.post("/query")
def query(req: QueryRequest):
    try:
        result = answer_query(req.question, req.mode)
        return {"answer": result["final_text"], "turns": result["turns"], "cache_read_tokens": result.get("cache_read_tokens", 0)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/feedback")
def feedback(req: FeedbackRequest):
    """
    Cheap, instant capture — deliberately makes NO agent call, so flagging a
    bad answer can never fail because of an LLM error. Distillation into
    lessons.md / page corrections happens separately via /distill.
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    entry = (
        f'## {timestamp} — status: unprocessed\n'
        f'Q: "{req.question}"\n'
        f'Bad answer: "{req.bad_answer}"\n'
        f'Correction: "{req.correction}"'
    )
    try:
        file_tools.append_log("feedback_log.md", entry)
        return {"status": "recorded"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/distill")
def distill():
    try:
        result = run_distillation()
        refreshed = refresh_token_counts()
        return {
            "summary": result["final_text"],
            "turns": result["turns"],
            "cache_read_tokens": result.get("cache_read_tokens", 0),
            "token_counts_refreshed": refreshed,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/lint")
def lint():
    """Report-only wiki health check. Writes lint-report.md, fixes nothing."""
    try:
        result = run_lint()
        return {"summary": result["final_text"], "turns": result["turns"], "cache_read_tokens": result.get("cache_read_tokens", 0)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/wiki/files")
def list_wiki_files(subdir: str = ""):
    return {"files": file_tools.list_files(subdir)}


@app.get("/wiki/file")
def get_wiki_file(path: str):
    try:
        return {"path": path, "content": file_tools.read_file(path)}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found")


@app.get("/health")
def health():
    return {"status": "ok"}
