"""
Cost estimation for the Náklady dashboard. Deterministic, no model calls —
takes the token-usage dict every agent loop now returns (see
agentic_loop.run_agent_loop) and converts it to an estimated cost.

This is an estimate for an internal dashboard, not a billing system: rates
are a point-in-time snapshot maintained by hand, and the USD->CZK
conversion (config.CZK_PER_USD) is a fixed approximation, not live FX.
"""

from backend.config import CZK_PER_USD, MODEL

# USD per token (not per million) for each usage field a response.usage
# object can carry. Cache-write isn't tracked yet (agentic_loop only reads
# cache_creation_input_tokens into the "cache_creation_tokens" field, see
# below) but the rate is included for when it is.
#
# claude-sonnet-5 intro pricing is in effect through 2026-08-31 ($2/$10 per
# MTok); it reverts to $3/$15 on 2026-09-01 — update PRICING then. Cache
# write is 1.25x input (5-min TTL); cache read is ~0.1x input.
PRICING_PER_MTOK = {
    "claude-sonnet-5": {
        "input": 2.00,
        "output": 10.00,
        "cache_creation": 2.50,
        "cache_read": 0.20,
    },
}

# Fallback used for any model not in the table above, so an unrecognized
# CLAUDE_MODEL doesn't crash cost estimation — just gives an approximate
# number rather than the exact one.
_FALLBACK_RATES = PRICING_PER_MTOK["claude-sonnet-5"]


def estimate_cost_usd(usage: dict, model: str = MODEL) -> float:
    """usage: {input_tokens, output_tokens, cache_creation_tokens,
    cache_read_tokens} — the shape run_agent_loop returns."""
    rates = PRICING_PER_MTOK.get(model, _FALLBACK_RATES)
    return (
        usage.get("input_tokens", 0) * rates["input"]
        + usage.get("output_tokens", 0) * rates["output"]
        + usage.get("cache_creation_tokens", 0) * rates["cache_creation"]
        + usage.get("cache_read_tokens", 0) * rates["cache_read"]
    ) / 1_000_000


def usd_to_czk(usd: float) -> float:
    return usd * CZK_PER_USD
