"""Full round-trip test for the capture pipeline against live Ollama + PostgreSQL."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from capture.pipeline import capture
from db_client.client import close_pool, get_pool, search_by_embedding
from capture.embedder import generate_embedding


async def main() -> None:
    # ------------------------------------------------------------------
    # 1. Store-worthy text should be captured
    # ------------------------------------------------------------------
    print("1. Testing capture of store-worthy text...")
    result = await capture(
        "We chose FastAPI over Flask for the new API gateway because it has "
        "native async support, automatic OpenAPI docs, and better performance "
        "under concurrent load. Tom benchmarked both frameworks last week.",
        source_client="test_runner",
    )
    assert result["stored"] is True
    assert result["id"] is not None
    stored_id = result["id"]
    print(f"   OK — stored with id={stored_id}")
    print(f"   reason: {result['reason']}")

    # ------------------------------------------------------------------
    # 2. Verify it's actually in the database via semantic search
    # ------------------------------------------------------------------
    print("2. Verifying entry is searchable via embedding...")
    query_emb = await generate_embedding("FastAPI vs Flask async performance")
    hits = await search_by_embedding(query_emb, limit=5)
    found = any(str(h["id"]) == stored_id for h in hits)
    assert found, "Stored entry not found in semantic search results"
    top = hits[0]
    print(f"   OK — found in search, similarity={top['similarity_score']:.4f}")
    print(f"   entry_type={top['entry_type']} topics={top['topics']}")

    # ------------------------------------------------------------------
    # 3. Duplicate should be skipped
    # ------------------------------------------------------------------
    print("3. Testing duplicate detection (same text again)...")
    dup_result = await capture(
        "We chose FastAPI over Flask for the new API gateway because it has "
        "native async support, automatic OpenAPI docs, and better performance "
        "under concurrent load. Tom benchmarked both frameworks last week.",
        source_client="test_runner",
    )
    assert dup_result["stored"] is False
    assert "duplicate" in dup_result["reason"].lower()
    print(f"   OK — duplicate rejected: {dup_result['reason']}")

    # ------------------------------------------------------------------
    # 4. Too-short text should be filtered
    # ------------------------------------------------------------------
    print("4. Testing rejection of too-short text...")
    short_result = await capture("ok thanks", source_client="test_runner")
    assert short_result["stored"] is False
    assert short_result["id"] is None
    print(f"   OK — filtered: {short_result['reason']}")

    # ------------------------------------------------------------------
    # 5. Chit-chat should be filtered
    # ------------------------------------------------------------------
    print("5. Testing rejection of chit-chat...")
    chat_result = await capture(
        "Hey! How's it going today? Hope you're having a great day!",
        source_client="test_runner",
    )
    assert chat_result["stored"] is False
    assert chat_result["id"] is None
    print(f"   OK — filtered: {chat_result['reason']}")

    # ------------------------------------------------------------------
    # 6. Second unique entry should also store
    # ------------------------------------------------------------------
    print("6. Testing capture of a second distinct entry...")
    result2 = await capture(
        "The Kubernetes pod was OOMKilled because the Java heap was set to 4GB "
        "but the container memory limit was only 3GB. Fixed by setting "
        "-XX:MaxRAMPercentage=75 instead of a fixed -Xmx value.",
        source_client="test_runner",
    )
    assert result2["stored"] is True
    stored_id_2 = result2["id"]
    print(f"   OK — stored with id={stored_id_2}")

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------
    print("7. Cleaning up test entries...")
    pool = await get_pool()
    await pool.execute("DELETE FROM brain_entries WHERE source_client = $1", "test_runner")
    remaining = await pool.fetchval("SELECT COUNT(*) FROM brain_entries")
    print(f"   Cleaned up. Remaining rows: {remaining}")

    await close_pool()
    print("\nAll pipeline tests passed!")


if __name__ == "__main__":
    asyncio.run(main())
