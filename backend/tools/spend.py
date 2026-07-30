"""
Deterministic spend/usage telemetry for the Náklady dashboard. Mirrors the
same "mechanical, not an LLM judgment call" pattern used elsewhere in
tools/ — nothing here calls the model, it just records and aggregates
token usage that agent loops already measured.

Storage: one JSON line per action in _system/spend.jsonl (config.
SPEND_LOG_PATH), read-modify-write appended via graph_client — same shape
of operation as file_tools.append_log, but not restricted to
log.md/feedback_log.md and not prose, so it lives in its own module rather
than being bolted onto append_log's allowlist.
"""

import json
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from backend.config import graph_client, SPEND_LOG_PATH, MODEL
from backend.graph_client import GraphNotFound
from backend.tools import pricing


def append_spend_record(action_type: str, usage: dict, model: str = None) -> None:
    """usage: {input_tokens, output_tokens, cache_creation_tokens,
    cache_read_tokens} — the shape agentic_loop.run_agent_loop returns."""
    model = model or MODEL
    cost_usd = pricing.estimate_cost_usd(usage, model)
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action_type": action_type,
        "model": model,
        "input_tokens": usage.get("input_tokens", 0),
        "output_tokens": usage.get("output_tokens", 0),
        "cache_creation_tokens": usage.get("cache_creation_tokens", 0),
        "cache_read_tokens": usage.get("cache_read_tokens", 0),
        "cost_usd": cost_usd,
        "cost_czk": pricing.usd_to_czk(cost_usd),
    }
    line = json.dumps(record, ensure_ascii=False) + "\n"
    try:
        existing = graph_client.read_file(SPEND_LOG_PATH)
    except GraphNotFound:
        existing = b""
    parent = SPEND_LOG_PATH.rsplit("/", 1)[0]
    graph_client.ensure_folder(parent)
    graph_client.write_file(SPEND_LOG_PATH, existing + line.encode("utf-8"))


def load_spend_records(since: Optional[datetime] = None) -> List[dict]:
    try:
        raw = graph_client.read_file(SPEND_LOG_PATH).decode("utf-8")
    except GraphNotFound:
        return []
    records = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if since is not None:
            try:
                if datetime.fromisoformat(rec["timestamp"]) < since:
                    continue
            except (KeyError, ValueError):
                continue
        records.append(rec)
    return records


def aggregate(records: List[dict]) -> dict:
    """Totals, per-action-type breakdown, and a fixed trailing-7-calendar-
    day series (zero-filled for days with no activity) — the exact shape
    the Náklady dashboard's KPI cards / table / trend chart consume."""
    totals = {"cache_tokens": 0, "new_tokens": 0, "cost_czk": 0.0, "count": 0}
    by_action: dict = {}
    daily_costs: dict = {}

    for rec in records:
        cache_tokens = rec.get("cache_read_tokens", 0)
        new_tokens = (
            rec.get("input_tokens", 0)
            + rec.get("output_tokens", 0)
            + rec.get("cache_creation_tokens", 0)
        )
        cost_czk = rec.get("cost_czk", 0.0)

        totals["cache_tokens"] += cache_tokens
        totals["new_tokens"] += new_tokens
        totals["cost_czk"] += cost_czk
        totals["count"] += 1

        action = rec.get("action_type", "other")
        bucket = by_action.setdefault(
            action, {"count": 0, "cache_tokens": 0, "new_tokens": 0, "cost_czk": 0.0}
        )
        bucket["count"] += 1
        bucket["cache_tokens"] += cache_tokens
        bucket["new_tokens"] += new_tokens
        bucket["cost_czk"] += cost_czk

        day = rec.get("timestamp", "")[:10]
        if day:
            daily_costs[day] = daily_costs.get(day, 0.0) + cost_czk

    total_tokens = totals["cache_tokens"] + totals["new_tokens"]
    cache_pct = round(100 * totals["cache_tokens"] / total_tokens) if total_tokens else 0

    today = datetime.now(timezone.utc).date()
    daily_series = [
        {
            "date": (today - timedelta(days=i)).isoformat(),
            "cost_czk": round(daily_costs.get((today - timedelta(days=i)).isoformat(), 0.0), 2),
        }
        for i in range(6, -1, -1)
    ]

    return {
        "total_cost_czk": round(totals["cost_czk"], 2),
        "total_tokens": total_tokens,
        "cache_pct": cache_pct,
        "action_count": totals["count"],
        "by_action": {
            action: {
                "count": b["count"],
                "cache_tokens": b["cache_tokens"],
                "new_tokens": b["new_tokens"],
                "cost_czk": round(b["cost_czk"], 2),
            }
            for action, b in by_action.items()
        },
        "daily": daily_series,
    }
