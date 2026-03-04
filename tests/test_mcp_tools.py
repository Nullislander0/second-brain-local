"""Test MCP tools against a seeded database.

Seeds directly via db_client + embedder to isolate the tools layer
from the classifier (which is tested separately).
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from capture.embedder import generate_embedding
from db_client.client import close_pool, get_pool, insert_entry
from mcp_server.tools.search import search_brain
from mcp_server.tools.recent import recent
from mcp_server.tools.stats import stats

SEED_ENTRIES = [
    {
        "text": (
            "We decided to migrate the payment service from REST to gRPC "
            "because internal service-to-service latency dropped by 40% in "
            "our benchmarks. Alice led the proof of concept."
        ),
        "entry_type": "decision",
        "topics": ["gRPC", "REST", "latency", "migration"],
        "people": ["Alice"],
        "projects": ["payment-service"],
        "action_items": [],
    },
    {
        "text": (
            "The Postgres connection pool was exhausting under load because "
            "each Lambda invocation opened a new connection. Switched to "
            "RDS Proxy and the issue resolved. This affected the Billing project."
        ),
        "entry_type": "observation",
        "topics": ["Postgres", "connection pooling", "Lambda", "RDS Proxy"],
        "people": [],
        "projects": ["Billing"],
        "action_items": [],
    },
    {
        "text": (
            "TODO: Write integration tests for the new search endpoint in the "
            "Open Brain project. Bob will own this task and target Friday."
        ),
        "entry_type": "action_item",
        "topics": ["integration tests", "search endpoint"],
        "people": ["Bob"],
        "projects": ["Open Brain"],
        "action_items": ["Write integration tests for search endpoint"],
    },
]


async def seed() -> list[str]:
    """Insert seed entries directly via db_client, return stored ids."""
    ids = []
    for entry in SEED_ENTRIES:
        emb = await generate_embedding(entry["text"])
        eid = await insert_entry(
            raw_text=entry["text"],
            embedding=emb,
            entry_type=entry["entry_type"],
            topics=entry["topics"],
            people=entry["people"],
            projects=entry["projects"],
            action_items=entry["action_items"],
            source_client="seed",
            relevance_score=0.95,
        )
        ids.append(str(eid))
    return ids


async def cleanup() -> None:
    pool = await get_pool()
    await pool.execute("DELETE FROM brain_entries WHERE source_client = $1", "seed")


async def main() -> None:
    print("Seeding database with 3 entries...")
    ids = await seed()
    print(f"  Seeded: {ids}\n")

    # ------------------------------------------------------------------
    # search_brain
    # ------------------------------------------------------------------
    print("1. search_brain — semantic query...")
    res = await search_brain("gRPC migration latency")
    assert "error" not in res, f"search_brain error: {res['error']}"
    assert res["count"] >= 1
    top = res["results"][0]
    assert "gRPC" in top["raw_text"]
    assert isinstance(top["id"], str)
    assert isinstance(top["similarity_score"], float)
    assert isinstance(top["created_at"], str)
    print(f"   OK — {res['count']} results, top similarity={top['similarity_score']}")

    print("2. search_brain — with entry_type filter...")
    res2 = await search_brain("task testing", entry_type="action_item")
    assert "error" not in res2
    for r in res2["results"]:
        assert r["entry_type"] == "action_item", f"Wrong type: {r['entry_type']}"
    print(f"   OK — {res2['count']} results, all action_item")

    print("3. search_brain — with project filter...")
    res3 = await search_brain("integration tests", project="Open Brain")
    assert "error" not in res3
    assert res3["count"] >= 1
    print(f"   OK — {res3['count']} results with project filter")

    # ------------------------------------------------------------------
    # recent_entries
    # ------------------------------------------------------------------
    print("4. recent_entries — last 1 day...")
    rec = await recent(days=1)
    assert "error" not in rec, f"recent error: {rec.get('error')}"
    assert rec["count"] >= 3
    # Should be newest first
    if rec["count"] >= 2:
        assert rec["results"][0]["created_at"] >= rec["results"][1]["created_at"]
    print(f"   OK — {rec['count']} results, newest first")

    print("5. recent_entries — with entry_type filter...")
    rec2 = await recent(days=1, entry_type="decision")
    assert "error" not in rec2
    for r in rec2["results"]:
        assert r["entry_type"] == "decision"
    print(f"   OK — {rec2['count']} decisions")

    # ------------------------------------------------------------------
    # brain_stats
    # ------------------------------------------------------------------
    print("6. brain_stats — 30-day window...")
    st = await stats(days=30)
    assert "error" not in st, f"stats error: {st.get('error')}"
    assert st["total_in_window"] >= 3
    assert st["total_all_time"] >= 3
    assert isinstance(st["by_entry_type"], dict)
    assert isinstance(st["top_topics"], dict)
    assert isinstance(st["top_projects"], dict)
    assert st["most_recent"] is not None
    print(f"   OK — total_in_window={st['total_in_window']}, "
          f"all_time={st['total_all_time']}")
    print(f"   by_type={st['by_entry_type']}")
    print(f"   top_topics={st['top_topics']}")
    print(f"   top_projects={st['top_projects']}")

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------
    print("\n7. Cleaning up seed data...")
    await cleanup()
    await close_pool()
    print("   Done.")

    print("\nAll MCP tool tests passed!")


if __name__ == "__main__":
    asyncio.run(main())
