"""Smoke tests for db_client against the live database."""

import asyncio
import random
import sys
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db_client.client import (
    brain_stats,
    close_pool,
    find_duplicate,
    get_pool,
    insert_entry,
    recent_entries,
    search_by_embedding,
)

DIM = 768


def _rand_embedding() -> list[float]:
    return [random.random() for _ in range(DIM)]


async def main() -> None:
    print("1. Testing connection pool...")
    pool = await get_pool()
    assert pool is not None
    print("   Pool created OK")

    print("2. Testing insert_entry...")
    emb = _rand_embedding()
    entry_id = await insert_entry(
        raw_text="The db_client smoke test works correctly.",
        embedding=emb,
        entry_type="observation",
        topics=["testing", "database"],
        people=["developer"],
        projects=["open-brain"],
        action_items=[],
        source_client="test_runner",
        relevance_score=0.9,
    )
    assert entry_id is not None
    print(f"   Inserted entry: {entry_id}")

    print("3. Testing find_duplicate (should find one)...")
    is_dup = await find_duplicate(emb, threshold=0.98)
    assert is_dup is True
    print("   Duplicate detected OK")

    print("4. Testing find_duplicate with different embedding (should not find)...")
    is_dup2 = await find_duplicate(_rand_embedding(), threshold=0.98)
    assert is_dup2 is False
    print("   No false duplicate OK")

    print("5. Testing search_by_embedding...")
    results = await search_by_embedding(emb, limit=5)
    assert len(results) >= 1
    assert results[0]["similarity_score"] > 0.99
    print(f"   Search returned {len(results)} results, top similarity: {results[0]['similarity_score']:.4f}")

    print("6. Testing search with entry_type filter...")
    results_filtered = await search_by_embedding(emb, limit=5, entry_type="observation")
    assert len(results_filtered) >= 1
    print(f"   Filtered search OK: {len(results_filtered)} results")

    print("7. Testing search with project filter...")
    results_proj = await search_by_embedding(emb, limit=5, project="open-brain")
    assert len(results_proj) >= 1
    print(f"   Project filter OK: {len(results_proj)} results")

    print("8. Testing recent_entries...")
    recent = await recent_entries(days=1)
    assert len(recent) >= 1
    assert recent[0]["raw_text"] == "The db_client smoke test works correctly."
    print(f"   Recent entries OK: {len(recent)} results")

    print("9. Testing brain_stats...")
    stats = await brain_stats(days=1)
    assert stats["total_in_window"] >= 1
    assert stats["total_all_time"] >= 1
    assert "observation" in stats["by_entry_type"]
    assert "testing" in stats["top_topics"]
    print(f"   Stats OK: {stats}")

    print("10. Cleanup: removing test entry...")
    pool = await get_pool()
    await pool.execute("DELETE FROM brain_entries WHERE id = $1", entry_id)
    remaining = await pool.fetchval("SELECT COUNT(*) FROM brain_entries")
    print(f"    Cleaned up. Remaining rows: {remaining}")

    await close_pool()
    print("\nAll db_client tests passed!")


if __name__ == "__main__":
    asyncio.run(main())
