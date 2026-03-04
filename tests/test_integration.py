"""Full integration test: ingest via capture pipeline, retrieve via MCP server.

Exercises the complete system end-to-end:
1. Capture pipeline stores entries (classifier → extractor → embedder → DB)
2. MCP server exposes them via search, recent, and stats tools
3. Duplicate detection prevents re-storage
4. Relevance gate filters junk
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from capture.pipeline import capture
from db_client.client import close_pool, get_pool

# --- Test data ---

STORE_WORTHY = [
    {
        "text": (
            "After profiling the image processing service, we found that 80% of "
            "CPU time was spent in the resize step. Switching from Pillow to "
            "libvips reduced processing time from 1.2s to 180ms per image. "
            "Elena benchmarked both libraries on the Atlas project."
        ),
        "source": "integration_test",
    },
    {
        "text": (
            "Important architectural decision for the Hermes project: we are "
            "migrating the notification service from HTTP polling to WebSockets "
            "because polling creates excessive load on the API gateway. Carlos "
            "will prototype the WebSocket implementation by end of sprint. We "
            "also need to reconfigure the AWS load balancer to support sticky "
            "sessions, since WebSocket connections must persist to the same backend."
        ),
        "source": "integration_test",
    },
    {
        "text": (
            "Discovered that Python 3.12 introduces a per-interpreter GIL which "
            "allows true parallelism for CPU-bound C extensions running in separate "
            "sub-interpreters. This is a significant finding for our data pipeline "
            "because it could eliminate the need for multiprocessing and its "
            "associated memory overhead when processing large datasets."
        ),
        "source": "integration_test",
    },
]

SHOULD_REJECT = [
    "ok",
    "Hey! What's up?",
    "Error: ECONNREFUSED 127.0.0.1:3000",
]


async def ingest_phase() -> list[str]:
    """Run the capture pipeline for all test inputs. Return stored IDs."""
    stored_ids = []

    # Store-worthy entries
    for entry in STORE_WORTHY:
        result = await capture(entry["text"], source_client=entry["source"])
        assert result["stored"], f"Expected storage but got: {result['reason']}"
        stored_ids.append(result["id"])
        print(f"  Stored: {result['id'][:8]}... — {result['reason']}")

    # Rejected entries
    for text in SHOULD_REJECT:
        result = await capture(text, source_client="integration_test")
        assert not result["stored"], f"Expected rejection for '{text}' but was stored"
        print(f"  Rejected: '{text[:30]}' — {result['reason'][:60]}")

    # Duplicate detection
    dup = await capture(STORE_WORTHY[0]["text"], source_client="integration_test")
    assert not dup["stored"], "Duplicate should have been rejected"
    assert "duplicate" in dup["reason"].lower()
    print(f"  Duplicate rejected OK")

    # Close pool so the MCP server subprocess can create its own
    await close_pool()
    return stored_ids


async def retrieval_phase(stored_ids: list[str]) -> None:
    """Start MCP server and verify all three tools return correct data."""
    server_script = str(Path(__file__).resolve().parent.parent / "mcp_server" / "server.py")
    server_params = StdioServerParameters(
        command=sys.executable,
        args=[server_script],
    )

    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            print("  MCP session initialized")

            # --- search_brain_tool ---
            # Query should find the image processing entry
            r = await session.call_tool(
                "search_brain_tool",
                arguments={"query": "image resize performance optimization libvips"},
            )
            data = json.loads(r.content[0].text)
            assert data["count"] >= 1, f"Search returned 0 results"
            top = data["results"][0]
            assert "libvips" in top["raw_text"] or "image" in top["raw_text"].lower()
            print(f"  search_brain_tool: {data['count']} results, "
                  f"top sim={top['similarity_score']}")

            # Filtered search by entry_type
            r2 = await session.call_tool(
                "search_brain_tool",
                arguments={"query": "WebSockets notification", "entry_type": "action_item"},
            )
            d2 = json.loads(r2.content[0].text)
            for row in d2["results"]:
                assert row["entry_type"] == "action_item"
            print(f"  search (entry_type filter): {d2['count']} action_items")

            # --- recent_entries ---
            r3 = await session.call_tool(
                "recent_entries",
                arguments={"days": 1},
            )
            d3 = json.loads(r3.content[0].text)
            assert d3["count"] >= 3, f"Expected >=3 recent, got {d3['count']}"
            # Verify ordering (newest first)
            timestamps = [row["created_at"] for row in d3["results"]]
            assert timestamps == sorted(timestamps, reverse=True), "Not newest-first"
            print(f"  recent_entries: {d3['count']} entries, newest-first OK")

            # --- brain_stats ---
            r4 = await session.call_tool(
                "brain_stats",
                arguments={"days": 30},
            )
            d4 = json.loads(r4.content[0].text)
            assert d4["total_in_window"] >= 3
            assert d4["total_all_time"] >= 3
            assert len(d4["top_topics"]) >= 1
            assert d4["most_recent"] is not None
            print(f"  brain_stats: {d4['total_in_window']} in window, "
                  f"{d4['total_all_time']} all time")
            print(f"    by_type: {d4['by_entry_type']}")
            print(f"    top_topics: {list(d4['top_topics'].keys())[:5]}")


async def cleanup_phase() -> None:
    pool = await get_pool()
    await pool.execute(
        "DELETE FROM brain_entries WHERE source_client = $1",
        "integration_test",
    )
    remaining = await pool.fetchval("SELECT count(*) FROM brain_entries")
    await close_pool()
    print(f"  Cleaned up. Remaining rows: {remaining}")


async def main() -> None:
    print("=" * 60)
    print("OPEN BRAIN — FULL INTEGRATION TEST")
    print("=" * 60)

    print("\n--- Phase 1: Ingest via capture pipeline ---")
    stored_ids = await ingest_phase()
    print(f"\n  Total stored: {len(stored_ids)}")

    print("\n--- Phase 2: Retrieve via MCP server ---")
    await retrieval_phase(stored_ids)

    print("\n--- Phase 3: Cleanup ---")
    await cleanup_phase()

    print("\n" + "=" * 60)
    print("ALL INTEGRATION TESTS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
