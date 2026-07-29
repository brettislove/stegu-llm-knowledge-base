"""
FastAPI backend for the knowledge base MVP — OneDrive-backed version of the
layered-index design (see SCHEMA.md and the Design Notes). Runs against a
business OneDrive drive via Microsoft Graph (wiki/, pending_review/,
archive/) instead of local disk — see graph_client.py / config.py for the
Graph plumbing.

Every route, request model, and public function name is unchanged from
the local-disk version. What changed internally: anywhere the old code
did direct pathlib.Path operations (mkdir/glob/write_bytes/unlink/read_text)
against WIKI_ROOT or PENDING_REVIEW_ROOT, this version calls the
corresponding file_tools.py function instead, so there's exactly one call
site per filesystem-shaped operation and main.py doesn't carry its own
parallel set of graph_client calls.

Run from the project root with:
    uvicorn backend.main:app --reload --port 8000
"""

import asyncio
import base64
import json
import uuid
from datetime import datetime, timezone
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
from backend.config import VALID_CATEGORY
from backend.auth import ClerkAuthMiddleware
from backend.graph_client import extract_content_hash

app = FastAPI(title="Knowledge Base MVP")

# Order matters: Starlette applies middleware in reverse of add order, so
# CORS (added second) runs outermost and can attach headers to the 401
# responses ClerkAuthMiddleware returns. Auth still runs before any route
# handler either way.
app.add_middleware(ClerkAuthMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://decorstone.sparxoft.com",
        "https://stegu-llm-knowledge-base.vercel.app/",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Single-writer discipline (Design Notes §6.1), adapted for a single
# process: one asyncio.Lock instead of a cloud lock file — avoids two
# concurrent uploads racing to edit the same index file. This was already
# just a same-process guard, not a cross-process/cross-machine lock, so
# moving to OneDrive as the backend doesn't change its guarantees one way
# or the other — it's still only safe as long as there's one backend
# process. If you ever run multiple backend instances against the same
# OneDrive drive, this in-memory lock stops being sufficient and you'd
# need a real distributed lock (e.g. a lock file in OneDrive with
# conflict-behavior=fail, or a database row lock).
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


def _build_llm_content(filename: str, file_base64: str, raw_bytes: bytes):
    if filename.lower().endswith(".pdf"):
        return [
            {
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": file_base64,
                },
            }
        ]
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

    raw_sibling_meta = file_tools.store_raw_sibling(destination_path, filename, raw_bytes)

    result = write_page(
        filename, content_for_llm, destination_path, governing_index, classification
    )

    # Prefer Graph's own sha256Hash for the stored/authoritative hash — the
    # local hash (already computed above for the pre-upload dedup check) is
    # only a fallback for when Graph doesn't populate it.
    raw_hash = extract_content_hash(raw_sibling_meta) or hashing.compute_hash_bytes(
        raw_bytes
    )
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

    raw_sibling_meta = file_tools.store_raw_sibling(destination_path, filename, raw_bytes)
    result = write_page(
        filename, content_for_llm, destination_path, governing_index, classification
    )
    return destination_path, category, topic, result, raw_sibling_meta


def _finalize(destination_path, category, topic, raw_bytes, result, raw_sibling_meta=None):
    raw_hash = extract_content_hash(raw_sibling_meta) or hashing.compute_hash_bytes(
        raw_bytes
    )
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


def _queue_for_review(filename: str, raw_bytes: bytes, classification: dict) -> dict:
    """Shared low-confidence path used by both /ingest and /ingest/stream.
    Writes the raw upload + a JSON metadata sidecar into pending_review/
    via file_tools' pending-review helpers (Graph-backed), instead of the
    old direct PENDING_REVIEW_ROOT.mkdir()/.write_bytes()/.write_text()."""
    qid = uuid.uuid4().hex[:12]
    ext = filename.rsplit(".", 1)[-1] if "." in filename else "bin"
    file_tools.pending_review_write(f"{qid}.{ext}", raw_bytes)
    meta = {
        "filename": filename,
        "classification": classification,
        "queued_at": datetime.now(timezone.utc).isoformat(),
        "ext": ext,
    }
    file_tools.pending_review_write(
        f"{qid}.json",
        json.dumps(meta, ensure_ascii=False, indent=2).encode("utf-8"),
    )
    return {
        "status": "pending_review",
        "queue_id": qid,
        "reasoning": classification.get("reasoning", ""),
        "proposed": classification,
        "message": "Low classification confidence — queued for human review (GET /pending-review).",
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
        result = _queue_for_review(req.filename, raw_bytes, classification)
        yield _sse({"stage": "finished", "result": result})
        return

    yield _sse({"stage": "write", "status": "start", "label": "Zápis stránky do wiki"})
    try:
        destination_path, category, topic, agent_result, raw_sibling_meta = (
            _write_and_finalize(
                req.filename, raw_bytes, classification, content_for_llm
            )
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
        result = _finalize(
            destination_path, category, topic, raw_bytes, agent_result, raw_sibling_meta
        )
    except Exception as e:
        yield _sse({"stage": "finalize", "status": "error", "message": str(e)})
        return
    yield _sse({"stage": "finalize", "status": "done"})

    yield _sse({"stage": "finished", "result": result})


@app.post("/ingest")
async def ingest(req: IngestRequest):
    async with _ingest_lock:
        try:
            file_tools.acquire_ingest_lock()
        except file_tools.IngestLockedError as e:
            raise HTTPException(status_code=409, detail=str(e))
        try:
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
                content_for_llm = _build_llm_content(
                    req.filename, req.file_base64, raw_bytes
                )
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))

            try:
                classification = classify_document(req.filename, content_for_llm)
            except Exception as e:
                raise HTTPException(
                    status_code=500, detail=f"Classification failed: {e}"
                )

            if classification.get("confidence") == "low":
                return _queue_for_review(req.filename, raw_bytes, classification)

            try:
                return _run_full_ingest(req.filename, raw_bytes, classification)
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
        finally:
            file_tools.release_ingest_lock()


@app.post("/ingest/stream")
async def ingest_stream(req: IngestRequest):
    async def gen():
        await _ingest_lock.acquire()
        try:
            file_tools.acquire_ingest_lock()
        except file_tools.IngestLockedError as e:
            _ingest_lock.release()
            yield _sse(
                {
                    "stage": "finished",
                    "result": {"status": "error", "message": str(e)},
                }
            )
            return
        try:
            for chunk in _ingest_pipeline(req):
                yield chunk
        finally:
            file_tools.release_ingest_lock()
            _ingest_lock.release()

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/pending-review")
def list_pending_review():
    items = []
    for meta_name in file_tools.pending_review_list_json():
        qid = meta_name[: -len(".json")]
        meta = json.loads(file_tools.pending_review_read_text(meta_name))
        items.append({"id": qid, **meta})
    return {"items": items}


@app.post("/pending-review/{queue_id}/approve")
async def approve_pending_review(
    queue_id: str, override: ReviewDecisionOverride = ReviewDecisionOverride()
):
    if not file_tools.pending_review_exists(f"{queue_id}.json"):
        raise HTTPException(status_code=404, detail="Unknown pending-review item.")
    meta = json.loads(file_tools.pending_review_read_text(f"{queue_id}.json"))
    classification = meta["classification"]
    for key, value in override.model_dump(exclude_none=True).items():
        classification[key] = value
    classification["confidence"] = "high"  # a human approved it

    raw_name = f"{queue_id}.{meta['ext']}"
    if not file_tools.pending_review_exists(raw_name):
        raise HTTPException(status_code=404, detail="Queued raw file missing.")
    raw_bytes = file_tools.pending_review_read_bytes(raw_name)

    async with _ingest_lock:
        try:
            file_tools.acquire_ingest_lock()
        except file_tools.IngestLockedError as e:
            raise HTTPException(status_code=409, detail=str(e))
        try:
            try:
                content_for_llm = _build_llm_content(
                    meta["filename"], base64.b64encode(raw_bytes).decode(), raw_bytes
                )
                destination_path, category, topic, agent_result, raw_sibling_meta = (
                    _write_and_finalize(
                        meta["filename"], raw_bytes, classification, content_for_llm
                    )
                )
                result = _finalize(
                    destination_path,
                    category,
                    topic,
                    raw_bytes,
                    agent_result,
                    raw_sibling_meta,
                )
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
        finally:
            file_tools.release_ingest_lock()

    file_tools.pending_review_delete(raw_name, missing_ok=True)
    file_tools.pending_review_delete(f"{queue_id}.json", missing_ok=True)
    return result


@app.post("/pending-review/{queue_id}/reject")
def reject_pending_review(queue_id: str):
    if not file_tools.pending_review_exists(f"{queue_id}.json"):
        raise HTTPException(status_code=404, detail="Unknown pending-review item.")
    meta = json.loads(file_tools.pending_review_read_text(f"{queue_id}.json"))
    file_tools.pending_review_delete(f"{queue_id}.{meta['ext']}", missing_ok=True)
    file_tools.pending_review_delete(f"{queue_id}.json")
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
            file_tools.acquire_ingest_lock()
        except file_tools.IngestLockedError as e:
            raise HTTPException(status_code=409, detail=str(e))
        try:
            result = split_category(category)
            return {"summary": result["final_text"], "turns": result["turns"]}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
        finally:
            file_tools.release_ingest_lock()


@app.get("/wiki/manifest")
def get_manifest():
    return hashing.load_manifest()


@app.post("/query")
def query(req: QueryRequest):
    try:
        result = answer_query(req.question, req.mode)
        return {
            "answer": result["final_text"],
            "turns": result["turns"],
            "cache_read_tokens": result.get("cache_read_tokens", 0),
        }
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
        f"## {timestamp} — status: unprocessed\n"
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
        return {
            "summary": result["final_text"],
            "turns": result["turns"],
            "cache_read_tokens": result.get("cache_read_tokens", 0),
        }
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
