"""Seed entries directly into the DB, bypassing the classifier."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from capture.embedder import generate_embedding
from db_client.client import insert_entry, find_duplicate


ENTRIES = [
    {
        "raw_text": (
            "Open Brain entry types and when they are used: 'observation' for facts, insights, and general knowledge; "
            "'decision' for choices made with reasoning; 'action_item' for tasks and commitments with deadlines; "
            "'reference' for technical details, configurations, and documentation; 'project_note' for updates "
            "and progress on specific projects. The classifier LLM chooses the type based on content analysis."
        ),
        "entry_type": "reference",
        "topics": ["Open Brain", "entry types", "classification"],
        "source_client": "seed",
    },
    {
        "raw_text": (
            "The MCP server exposes four tools: capture_text (store new entries programmatically), "
            "search_brain (semantic similarity search using vector embeddings), recent_entries (retrieve "
            "the latest N entries, optionally filtered by source), and brain_stats (total entries, entries "
            "by type, top topics, recent activity, and storage size). The MCP server uses stdio transport "
            "and is configured in .mcp.json for use with Claude Code or other MCP-compatible clients."
        ),
        "entry_type": "reference",
        "topics": ["Open Brain", "MCP server", "tools", "search"],
        "source_client": "seed",
    },
]


async def main():
    for i, entry in enumerate(ENTRIES, 1):
        print(f"[{i}/{len(ENTRIES)}] Embedding: {entry['raw_text'][:70]}...")
        embedding = await generate_embedding(entry["raw_text"])

        if await find_duplicate(embedding):
            print("  SKIPPED: duplicate")
            continue

        entry_id = await insert_entry(
            raw_text=entry["raw_text"],
            embedding=embedding,
            entry_type=entry["entry_type"],
            topics=entry["topics"],
            people=[],
            projects=["Open Brain"],
            action_items=[],
            source_client=entry["source_client"],
            relevance_score=1.0,
        )
        print(f"  STORED: {entry_id}")

    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
