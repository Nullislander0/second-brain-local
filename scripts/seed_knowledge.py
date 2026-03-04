"""Seed the brain with foundational knowledge about itself."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

API = "http://localhost:8100"

ENTRIES = [
    {
        "text": (
            "Open Brain is a local second brain system built on PostgreSQL with pgvector. "
            "It passively captures context from AI conversations, classifies relevance using "
            "a local LLM (qwen3:8b via Ollama), extracts metadata like topics, people, projects, "
            "and action items, generates 1024-dimensional vector embeddings using mxbai-embed-large, "
            "checks for near-duplicates, and stores everything locally. Nothing leaves the machine."
        ),
        "source_client": "seed",
    },
    {
        "text": (
            "The Open Brain capture pipeline has four stages: (1) a relevance gate classifier that "
            "filters out chit-chat, greetings, and system noise — only substantive content passes through, "
            "(2) concurrent metadata extraction (entry type, topics, people, projects, action items) and "
            "vector embedding generation, (3) duplicate detection via cosine similarity (>0.98 threshold), "
            "and (4) storage in PostgreSQL. The classifier uses a fail-open design — if Ollama is unreachable, "
            "content defaults to being stored rather than silently lost."
        ),
        "source_client": "seed",
    },
    {
        "text": (
            "The Open Brain technology stack: PostgreSQL 16 with pgvector for vector storage and similarity search, "
            "Ollama for local LLM inference (mxbai-embed-large for embeddings, qwen3:8b for classification and extraction), "
            "FastAPI for the capture HTTP API on port 8100, Open WebUI as the chat interface on port 3000, "
            "Open WebUI Pipelines for the message capture filter, an MCP server (stdio transport via FastMCP) "
            "exposing search, recent entries, stats, and capture tools, and Docker Compose orchestrating all services. "
            "Everything runs on localhost with no external dependencies."
        ),
        "source_client": "seed",
    },
    {
        "text": (
            "The brain database schema: brain_entries table with UUID primary key, raw_text (original content), "
            "embedding (vector(1024)), entry_type (observation/decision/action_item/reference/project_note), "
            "topics array, people array, projects array, action_items array, source_client (who sent it), "
            "relevance_score (classifier confidence), and created_at timestamp. Indexes: IVFFlat on embedding "
            "for fast cosine similarity search, GIN on topics/projects for array lookups, btree on created_at."
        ),
        "source_client": "seed",
    },
    {
        "text": (
            "Open Brain entry types and when they are used: 'observation' for facts, insights, and general knowledge; "
            "'decision' for choices made with reasoning; 'action_item' for tasks and commitments with deadlines; "
            "'reference' for technical details, configurations, and documentation; 'project_note' for updates "
            "and progress on specific projects. The classifier LLM chooses the type based on content analysis."
        ),
        "source_client": "seed",
    },
    {
        "text": (
            "Open Brain was built in March 2026 as a personal knowledge management system. The design philosophy "
            "is passive capture — the user shouldn't need to manually tag, file, or organize anything. "
            "Conversations naturally become searchable memory. The system is designed to eventually be shareable "
            "with friends. Future planned features include a token budget tracker for paid LLM APIs, "
            "PDF ingestion and web scraping, and a Telegram bot for mobile journaling."
        ),
        "source_client": "seed",
    },
    {
        "text": (
            "The Open WebUI integration works via a Pipeline filter called 'Open Brain Capture'. "
            "Every user message sent through the chat interface is intercepted by the filter's inlet() method, "
            "which forwards it to the capture API at http://capture-api:8100/capture. The capture is fire-and-forget — "
            "it never blocks or slows down the chat. Assistant responses can optionally be captured too "
            "by enabling capture_assistant_responses in the filter's Valves settings."
        ),
        "source_client": "seed",
    },
    {
        "text": (
            "The MCP server exposes four tools: capture_text (store new entries programmatically), "
            "search_brain (semantic similarity search using vector embeddings), recent_entries (retrieve "
            "the latest N entries, optionally filtered by source), and brain_stats (total entries, entries "
            "by type, top topics, recent activity, and storage size). The MCP server uses stdio transport "
            "and is configured in .mcp.json for use with Claude Code or other MCP-compatible clients."
        ),
        "source_client": "seed",
    },
]


async def main():
    async with httpx.AsyncClient(timeout=180) as client:
        for i, entry in enumerate(ENTRIES, 1):
            print(f"[{i}/{len(ENTRIES)}] Sending: {entry['text'][:70]}...")
            for attempt in range(3):
                try:
                    resp = await client.post(f"{API}/capture", json=entry)
                    result = resp.json()
                    status = "STORED" if result.get("stored") else "SKIPPED"
                    print(f"  {status}: {result.get('reason', '')[:80]}")
                    break
                except httpx.ReadTimeout:
                    if attempt < 2:
                        print(f"  Timeout, retrying ({attempt + 2}/3)...")
                    else:
                        print(f"  FAILED after 3 attempts (timeout)")
            print()

    print("Done seeding.")


if __name__ == "__main__":
    asyncio.run(main())
