"""Main capture pipeline — classifies, extracts metadata, embeds, and stores."""

from __future__ import annotations

import logging
from typing import Any

from capture.classifier import classify
from capture.embedder import generate_embedding
from capture.extractor import extract_metadata
from db_client.client import find_duplicate, insert_entry

logger = logging.getLogger(__name__)


async def capture(text: str, source_client: str = "unknown") -> dict[str, Any]:
    """Capture a piece of text into the brain.

    Returns: {"stored": bool, "id": str|None, "reason": str}
    """
    # Step 1 — Relevance gate
    classification = await classify(text)
    if not classification.should_store:
        logger.info(
            "Rejected: label=%s reason=%s",
            classification.label,
            classification.reason,
        )
        return {
            "stored": False,
            "id": None,
            "reason": f"Filtered by relevance gate: {classification.label} — {classification.reason}",
        }

    # Step 2 & 3 — Metadata extraction and embedding generation run concurrently
    import asyncio

    metadata_task = asyncio.create_task(extract_metadata(text))
    embedding_task = asyncio.create_task(generate_embedding(text))

    metadata = await metadata_task
    embedding = await embedding_task

    # Step 3.5 — Duplicate detection
    if await find_duplicate(embedding):
        logger.info("Duplicate detected, skipping storage")
        return {
            "stored": False,
            "id": None,
            "reason": "Near-duplicate entry already exists (cosine similarity > 0.98)",
        }

    # Step 4 — Store
    entry_id = await insert_entry(
        raw_text=text,
        embedding=embedding,
        entry_type=metadata.entry_type,
        topics=metadata.topics,
        people=metadata.people,
        projects=metadata.projects,
        action_items=metadata.action_items,
        source_client=source_client,
        relevance_score=classification.confidence,
    )

    logger.info(
        "Stored entry %s: type=%s topics=%s",
        entry_id,
        metadata.entry_type,
        metadata.topics,
    )
    return {
        "stored": True,
        "id": str(entry_id),
        "reason": f"Stored as {metadata.entry_type} (confidence {classification.confidence:.2f})",
    }
