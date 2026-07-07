"""
FastAPI backend for the knowledge base MVP.

Run from the project root with:
    uvicorn backend.main:app --reload --port 8000
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.agents.ingest_agent import ingest_document
from backend.agents.query_agent import answer_query
from backend.agents.distill_agent import run_distillation
from backend.agents.lint_agent import run_lint
from backend.tools import file_tools
from backend.converters import convert_file  # New import

app = FastAPI(title="Knowledge Base MVP")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # fine for local MVP testing; tighten before any real deployment
    allow_methods=["*"],
    allow_headers=["*"],
)


class IngestRequest(BaseModel):
    filename: str
    file_base64: str  # Unified raw base64 string for all extensions


class QueryRequest(BaseModel):
    question: str
    mode: str = "internal"  # "internal" | "public"


class FeedbackRequest(BaseModel):
    question: str
    bad_answer: str
    correction: str


@app.post("/ingest")
def ingest(req: IngestRequest):
    try:
        # Route through converter module first to preserve original ingest_document logic
        pdf_base64, markdown = convert_file(req.filename, req.file_base64)
        
        result = ingest_document(req.filename, pdf_base64=pdf_base64, markdown=markdown)
        return {
            "summary": result["final_text"], 
            "turns": result["turns"], 
            "cache_read_tokens": result.get("cache_read_tokens", 0)
        }
    except ValueError as e:
        # Clean catch for unsupported extensions or malformed parsing
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
        return {"summary": result["final_text"], "turns": result["turns"], "cache_read_tokens": result.get("cache_read_tokens", 0)}
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