"""Async PostgreSQL client with connection pooling for Open Brain."""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import UUID

import asyncpg
from pgvector.asyncpg import register_vector

import config

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None
_pool_lock = asyncio.Lock()


async def get_pool() -> asyncpg.Pool:
    """Return the shared connection pool, creating it on first call."""
    global _pool
    if _pool is not None and not _pool._closed:
        return _pool
    async with _pool_lock:
        # Double-check after acquiring lock
        if _pool is not None and not _pool._closed:
            return _pool
        _pool = await asyncpg.create_pool(
            host=config.POSTGRES_HOST,
            port=config.POSTGRES_PORT,
            database=config.POSTGRES_DB,
            user=config.POSTGRES_USER,
            password=config.POSTGRES_PASSWORD,
            min_size=2,
            max_size=10,
            init=_init_connection,
        )
        logger.info("Database connection pool created")
        return _pool


async def _init_connection(conn: asyncpg.Connection) -> None:
    """Called for every new connection — register pgvector type codec."""
    await register_vector(conn)


async def close_pool() -> None:
    """Gracefully close the connection pool."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("Database connection pool closed")


# ---------------------------------------------------------------------------
# Write operations
# ---------------------------------------------------------------------------

async def insert_entry(
    raw_text: str,
    embedding: list[float],
    entry_type: str,
    topics: list[str],
    people: list[str],
    projects: list[str],
    action_items: list[str],
    source_client: str,
    relevance_score: float,
) -> UUID:
    """Insert a brain entry and return its id."""
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO brain_entries
            (raw_text, embedding, entry_type, topics, people,
             projects, action_items, source_client, relevance_score)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        RETURNING id
        """,
        raw_text,
        embedding,
        entry_type,
        topics,
        people,
        projects,
        action_items,
        source_client,
        relevance_score,
    )
    return row["id"]


async def find_duplicate(embedding: list[float], threshold: float = 0.98) -> bool:
    """Return True if a near-duplicate embedding already exists."""
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        SELECT 1
        FROM brain_entries
        WHERE 1 - (embedding <=> $1) > $2
        LIMIT 1
        """,
        embedding,
        threshold,
    )
    return row is not None


# ---------------------------------------------------------------------------
# Read operations
# ---------------------------------------------------------------------------

async def search_by_embedding(
    query_embedding: list[float],
    limit: int = 10,
    entry_type: str | None = None,
    project: str | None = None,
) -> list[dict[str, Any]]:
    """Semantic search: return entries ranked by cosine similarity."""
    conditions = []
    params: list[Any] = [query_embedding, limit]
    idx = 3  # next param index

    if entry_type:
        conditions.append(f"entry_type = ${idx}")
        params.append(entry_type)
        idx += 1
    if project:
        conditions.append(f"${idx} = ANY(projects)")
        params.append(project)
        idx += 1

    where = ""
    if conditions:
        where = "WHERE " + " AND ".join(conditions)

    sql = f"""
        SELECT id, raw_text, entry_type, topics, projects, people,
               action_items, source_client, relevance_score, created_at,
               1 - (embedding <=> $1) AS similarity_score
        FROM brain_entries
        {where}
        ORDER BY embedding <=> $1
        LIMIT $2
    """

    pool = await get_pool()
    rows = await pool.fetch(sql, *params)
    return [dict(r) for r in rows]


async def recent_entries(
    days: int = 7,
    entry_type: str | None = None,
    project: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Return entries from the last N days, newest first."""
    conditions = [f"created_at >= NOW() - INTERVAL '{days} days'"]
    params: list[Any] = [limit]
    idx = 2

    if entry_type:
        conditions.append(f"entry_type = ${idx}")
        params.append(entry_type)
        idx += 1
    if project:
        conditions.append(f"${idx} = ANY(projects)")
        params.append(project)
        idx += 1

    where = "WHERE " + " AND ".join(conditions)

    sql = f"""
        SELECT id, raw_text, entry_type, topics, projects, people,
               action_items, source_client, relevance_score, created_at
        FROM brain_entries
        {where}
        ORDER BY created_at DESC
        LIMIT $1
    """

    pool = await get_pool()
    rows = await pool.fetch(sql, *params)
    return [dict(r) for r in rows]


async def brain_stats(days: int = 30) -> dict[str, Any]:
    """Return summary statistics for the brain."""
    pool = await get_pool()

    stats_sql = f"""
        SELECT
            COUNT(*)::int AS total_in_window,
            MAX(created_at) AS most_recent
        FROM brain_entries
        WHERE created_at >= NOW() - INTERVAL '{days} days'
    """

    type_sql = f"""
        SELECT entry_type, COUNT(*)::int AS cnt
        FROM brain_entries
        WHERE created_at >= NOW() - INTERVAL '{days} days'
        GROUP BY entry_type
        ORDER BY cnt DESC
    """

    topics_sql = f"""
        SELECT unnest(topics) AS topic, COUNT(*)::int AS cnt
        FROM brain_entries
        WHERE created_at >= NOW() - INTERVAL '{days} days'
        GROUP BY topic
        ORDER BY cnt DESC
        LIMIT 10
    """

    projects_sql = f"""
        SELECT unnest(projects) AS project, COUNT(*)::int AS cnt
        FROM brain_entries
        WHERE created_at >= NOW() - INTERVAL '{days} days'
        GROUP BY project
        ORDER BY cnt DESC
        LIMIT 10
    """

    total_sql = "SELECT COUNT(*)::int AS total FROM brain_entries"

    # Run all queries concurrently
    summary, types, topics, projects, total = await asyncio.gather(
        pool.fetchrow(stats_sql),
        pool.fetch(type_sql),
        pool.fetch(topics_sql),
        pool.fetch(projects_sql),
        pool.fetchrow(total_sql),
    )

    return {
        "total_in_window": summary["total_in_window"],
        "most_recent": summary["most_recent"],
        "by_entry_type": {r["entry_type"]: r["cnt"] for r in types},
        "top_topics": {r["topic"]: r["cnt"] for r in topics},
        "top_projects": {r["project"]: r["cnt"] for r in projects},
        "total_all_time": total["total"],
    }
