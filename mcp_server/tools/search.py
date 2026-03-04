"""MCP tool: search_brain — semantic search over stored entries."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from capture.embedder import generate_embedding
from db_client.client import search_by_embedding

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


async def search_brain(
    query: str,
    limit: int = 10,
    entry_type: str | None = None,
    project: str | None = None,
) -> dict[str, Any]:
    """Semantic search over brain entries.

    Returns a dict with 'results' list and 'count'.
    """
    try:
        query_embedding = await generate_embedding(query)
        rows = await search_by_embedding(
            query_embedding,
            limit=min(limit, 50),
            entry_type=entry_type or None,
            project=project or None,
        )
        results = [_serialize_row(r) for r in rows]
        return {"results": results, "count": len(results)}
    except Exception as exc:
        logger.error("search_brain failed: %s", exc)
        return {"error": str(exc), "results": [], "count": 0}
