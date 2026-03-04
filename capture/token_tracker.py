"""Lightweight token usage logger — records every LLM/embedding call."""

from __future__ import annotations

import logging
import time
from decimal import Decimal

import config
from db_client.client import get_pool

logger = logging.getLogger(__name__)

_last_budget_check: float = 0
_BUDGET_CHECK_INTERVAL = 60  # seconds


def _get_cost(
    provider: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> Decimal:
    """Look up cost from config. Returns 0 for local/unknown models."""
    costs = getattr(config, "TOKEN_COSTS", {})
    # Try exact match first, then provider-level default
    key = f"{provider}/{model}"
    rate = costs.get(key, costs.get(provider, {}))
    if not rate:
        return Decimal("0")
    prompt_cost = Decimal(str(rate.get("prompt_per_1k", 0))) * prompt_tokens / 1000
    completion_cost = Decimal(str(rate.get("completion_per_1k", 0))) * completion_tokens / 1000
    return prompt_cost + completion_cost


async def log_usage(
    provider: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int = 0,
    operation: str = "chat",
) -> None:
    """Log a token usage record. Fire-and-forget — never raises."""
    try:
        cost = _get_cost(provider, model, prompt_tokens, completion_tokens)
        pool = await get_pool()
        await pool.execute(
            """
            INSERT INTO token_usage
                (provider, model, operation, prompt_tokens, completion_tokens, estimated_cost)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            provider,
            model,
            operation,
            prompt_tokens,
            completion_tokens,
            cost,
        )
        logger.debug(
            "Token usage: %s/%s %s — %d prompt + %d completion = %d total (cost $%s)",
            provider, model, operation,
            prompt_tokens, completion_tokens,
            prompt_tokens + completion_tokens,
            cost,
        )
        await _check_budget()
    except Exception as exc:
        logger.warning("Token tracking failed (non-fatal): %s", exc)


async def _check_budget() -> None:
    """Soft budget check — log warnings, never block."""
    global _last_budget_check
    now = time.time()
    if now - _last_budget_check < _BUDGET_CHECK_INTERVAL:
        return
    _last_budget_check = now

    budget = getattr(config, "MONTHLY_TOKEN_BUDGET", 0)
    if budget <= 0:
        return

    try:
        pool = await get_pool()
        row = await pool.fetchrow("""
            SELECT COALESCE(SUM(estimated_cost), 0)::numeric AS monthly_cost
            FROM token_usage
            WHERE created_at >= date_trunc('month', NOW())
        """)
        monthly_cost = float(row["monthly_cost"])
        pct = monthly_cost / budget

        if pct >= 1.0:
            logger.warning(
                "TOKEN BUDGET EXCEEDED: $%.4f / $%.2f (%.0f%%)",
                monthly_cost, budget, pct * 100,
            )
        elif pct >= 0.8:
            logger.warning(
                "TOKEN BUDGET WARNING: $%.4f / $%.2f (%.0f%%)",
                monthly_cost, budget, pct * 100,
            )
    except Exception as exc:
        logger.debug("Budget check failed (non-fatal): %s", exc)


async def get_stats(days: int = 30) -> dict:
    """Return token usage stats for the dashboard and MCP tool."""
    pool = await get_pool()
    interval = f"{days} days"

    # Summary
    summary = await pool.fetchrow(f"""
        SELECT
            COALESCE(SUM(total_tokens), 0)::bigint AS total_tokens,
            COALESCE(SUM(estimated_cost), 0)::numeric AS total_cost,
            COUNT(*)::int AS total_requests
        FROM token_usage
        WHERE created_at >= NOW() - INTERVAL '{interval}'
    """)

    # Today
    today = await pool.fetchrow("""
        SELECT COALESCE(SUM(total_tokens), 0)::bigint AS tokens,
               COALESCE(SUM(estimated_cost), 0)::numeric AS cost
        FROM token_usage
        WHERE created_at >= date_trunc('day', NOW())
    """)

    # This month
    month = await pool.fetchrow("""
        SELECT COALESCE(SUM(total_tokens), 0)::bigint AS tokens,
               COALESCE(SUM(estimated_cost), 0)::numeric AS cost
        FROM token_usage
        WHERE created_at >= date_trunc('month', NOW())
    """)

    # By provider
    by_provider = await pool.fetch(f"""
        SELECT provider,
               COALESCE(SUM(total_tokens), 0)::bigint AS tokens,
               COALESCE(SUM(estimated_cost), 0)::numeric AS cost,
               COUNT(*)::int AS requests
        FROM token_usage
        WHERE created_at >= NOW() - INTERVAL '{interval}'
        GROUP BY provider ORDER BY tokens DESC
    """)

    # By model
    by_model = await pool.fetch(f"""
        SELECT provider, model,
               COALESCE(SUM(prompt_tokens), 0)::bigint AS prompt,
               COALESCE(SUM(completion_tokens), 0)::bigint AS completion,
               COALESCE(SUM(total_tokens), 0)::bigint AS total,
               COALESCE(SUM(estimated_cost), 0)::numeric AS cost,
               COUNT(*)::int AS requests
        FROM token_usage
        WHERE created_at >= NOW() - INTERVAL '{interval}'
        GROUP BY provider, model ORDER BY total DESC
    """)

    # By operation
    by_operation = await pool.fetch(f"""
        SELECT operation,
               COALESCE(SUM(total_tokens), 0)::bigint AS tokens,
               COUNT(*)::int AS requests
        FROM token_usage
        WHERE created_at >= NOW() - INTERVAL '{interval}'
        GROUP BY operation ORDER BY tokens DESC
    """)

    # Daily trend
    daily = await pool.fetch(f"""
        SELECT date_trunc('day', created_at)::date AS day,
               COALESCE(SUM(total_tokens), 0)::bigint AS tokens,
               COALESCE(SUM(estimated_cost), 0)::numeric AS cost
        FROM token_usage
        WHERE created_at >= NOW() - INTERVAL '{interval}'
        GROUP BY day ORDER BY day
    """)

    # Budget status
    budget = getattr(config, "MONTHLY_TOKEN_BUDGET", 0)
    monthly_cost = float(month["cost"])
    if budget > 0:
        pct = round(monthly_cost / budget * 100, 1)
        if pct >= 100:
            status = "exceeded"
        elif pct >= 80:
            status = "warning"
        else:
            status = "ok"
    else:
        pct = 0
        status = "no_budget"

    return {
        "summary": {
            "total_tokens": int(summary["total_tokens"]),
            "total_cost": float(summary["total_cost"]),
            "total_requests": summary["total_requests"],
        },
        "today": {"tokens": int(today["tokens"]), "cost": float(today["cost"])},
        "month": {"tokens": int(month["tokens"]), "cost": float(month["cost"])},
        "by_provider": [
            {"provider": r["provider"], "tokens": int(r["tokens"]),
             "cost": float(r["cost"]), "requests": r["requests"]}
            for r in by_provider
        ],
        "by_model": [
            {"provider": r["provider"], "model": r["model"],
             "prompt": int(r["prompt"]), "completion": int(r["completion"]),
             "total": int(r["total"]), "cost": float(r["cost"]),
             "requests": r["requests"]}
            for r in by_model
        ],
        "by_operation": [
            {"operation": r["operation"], "tokens": int(r["tokens"]),
             "requests": r["requests"]}
            for r in by_operation
        ],
        "daily": [
            {"day": str(r["day"]), "tokens": int(r["tokens"]),
             "cost": float(r["cost"])}
            for r in daily
        ],
        "budget": {
            "monthly_limit": budget,
            "monthly_spent": monthly_cost,
            "percent_used": pct,
            "status": status,
        },
    }
