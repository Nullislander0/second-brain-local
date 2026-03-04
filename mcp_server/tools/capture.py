"""MCP tool: capture_text — store text in the brain via the capture pipeline."""

from __future__ import annotations

import logging
from typing import Any

from capture.pipeline import capture

logger = logging.getLogger(__name__)


async def capture_text(
    text: str,
    source_client: str = "mcp",
) -> dict[str, Any]:
    """Capture text into the brain.

    Returns: {"stored": bool, "id": str|None, "reason": str}
    """
    try:
        return await capture(text=text, source_client=source_client)
    except Exception as exc:
        logger.error("capture_text failed: %s", exc)
        return {"stored": False, "id": None, "reason": f"Error: {exc}"}
