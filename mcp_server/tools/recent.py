"""MCP tool: recent_entries — list entries from the last N days."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from db_client.client import recent_entries as db_recent_entries

logger = logging.getLogger(__name__)


def _serialize_row(row: dict[str, Any]) -> dict[str, Any]:
    """Convert DB row types to JSON-safe values."""
    out = {}
    for k, v in row.items():
        if isinstance(v, UUID):
            out[k] = str(v)
        elif isinstance(v, datetime):
            out[k] = v.isoformat()
        elif isinstance(v, float):
            out[k] = round(v, 4)
        else:
            out[k] = v
    return out


async def recent(
    days: int = 7,
    entry_type: str | None = None,
    project: str | None = None,
) -> dict[str, Any]:
    """List entries from the last N days, newest first.

    Returns a dict with 'results' list and 'count'.
    """
    try:
        rows = await db_recent_entries(
            days=max(1, days),
            entry_type=entry_type or None,
            project=project or None,
        )
        results = [_serialize_row(r) for r in rows]
        return {"results": results, "count": len(results)}
    except Exception as exc:
        logger.error("recent_entries failed: %s", exc)
        return {"error": str(exc), "results": [], "count": 0}
