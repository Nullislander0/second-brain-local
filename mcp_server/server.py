"""Open Brain MCP server — stdio transport exposing four tools."""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402 — must come after path setup
from mcp.server.fastmcp import FastMCP  # noqa: E402

from mcp_server.tools.capture import capture_text  # noqa: E402
from mcp_server.tools.search import search_brain  # noqa: E402
from mcp_server.tools.recent import recent  # noqa: E402
from mcp_server.tools.stats import stats  # noqa: E402
from db_client.client import close_pool  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("open-brain")

mcp = FastMCP(config.MCP_SERVER_NAME)


# ---------------------------------------------------------------------------
# Tool 0: capture_text
# ---------------------------------------------------------------------------
@mcp.tool()
async def capture_text_tool(
    text: str,
    source_client: str = "claude_code",
) -> dict:
    """Store a piece of text in your personal knowledge base.

    The text is automatically classified, tagged with metadata (topics,
    people, projects, action items), embedded for semantic search, and
    stored. Junk, chit-chat, and near-duplicates are filtered out.

    Use this to remember important information from conversations:
    decisions, insights, action items, observations, references.

    Args:
        text: The text to capture and store.
        source_client: Where this came from (default "claude_code").
    """
    return await capture_text(text=text, source_client=source_client)


# ---------------------------------------------------------------------------
# Tool 1: search_brain
# ---------------------------------------------------------------------------
@mcp.tool()
async def search_brain_tool(
    query: str,
    limit: int = 10,
    entry_type: str = "",
    project: str = "",
) -> dict:
    """Semantic search over your personal knowledge base.

    Search stored observations, decisions, action items, references,
    and project notes using natural language.

    Args:
        query: Natural language search query.
        limit: Maximum results to return (default 10, max 50).
        entry_type: Optional filter — one of: observation, decision,
                    action_item, reference, project_note.
        project: Optional filter — match entries tagged with this project name.
    """
    return await search_brain(
        query=query,
        limit=limit,
        entry_type=entry_type or None,
        project=project or None,
    )


# ---------------------------------------------------------------------------
# Tool 2: recent_entries
# ---------------------------------------------------------------------------
@mcp.tool()
async def recent_entries(
    days: int = 7,
    entry_type: str = "",
    project: str = "",
) -> dict:
    """List recent entries from your knowledge base.

    Returns entries from the last N days, newest first (max 50).

    Args:
        days: Lookback window in days (default 7).
        entry_type: Optional filter — one of: observation, decision,
                    action_item, reference, project_note.
        project: Optional filter — match entries tagged with this project name.
    """
    return await recent(
        days=days,
        entry_type=entry_type or None,
        project=project or None,
    )


# ---------------------------------------------------------------------------
# Tool 3: brain_stats
# ---------------------------------------------------------------------------
@mcp.tool()
async def brain_stats(days: int = 30) -> dict:
    """Get summary statistics and patterns from your knowledge base.

    Returns total entries, breakdown by type, top topics, top projects,
    and the most recent entry timestamp.

    Args:
        days: Window in days for stats (default 30).
    """
    return await stats(days=days)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    logger.info("Starting Open Brain MCP server (stdio)...")
    try:
        mcp.run(transport="stdio")
    finally:
        # Ensure the DB pool is cleaned up
        try:
            asyncio.get_event_loop().run_until_complete(close_pool())
        except Exception:
            pass


if __name__ == "__main__":
    main()
