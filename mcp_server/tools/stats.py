"""MCP tool: brain_stats — summary statistics and patterns."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from db_client.client import brain_stats as db_brain_stats

logger = logging.getLogger(__name__)


async def stats(days: int = 30) -> dict[str, Any]:
    """Return summary statistics for the brain.

    Returns a dict with totals, breakdowns, and top topics/projects.
    """
    try:
        raw = await db_brain_stats(days=max(1, days))
        # Serialize datetime
        most_recent = raw.get("most_recent")
        if isinstance(most_recent, datetime):
            raw["most_recent"] = most_recent.isoformat()
        elif most_recent is None:
            raw["most_recent"] = None
        return raw
    except Exception as exc:
        logger.error("brain_stats failed: %s", exc)
        return {"error": str(exc)}
