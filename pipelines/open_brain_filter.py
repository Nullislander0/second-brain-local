"""
title: Open Brain Filter
description: Captures user messages into the Open Brain knowledge base and injects relevant memories into the conversation context. Runs the relevance gate automatically — only substantive content is stored.
author: open-brain
version: 2.0
requirements: aiohttp
"""

from typing import List, Optional
from pydantic import BaseModel, Field
import aiohttp
import json


class Pipeline:
    class Valves(BaseModel):
        pipelines: List[str] = ["*"]
        priority: int = 0
        capture_api_url: str = Field(
            default="http://capture-api:8100",
            description="URL of the Open Brain capture API (use container name when running in Docker)",
        )
        capture_user_messages: bool = Field(
            default=True,
            description="Capture user messages to the brain",
        )
        capture_assistant_responses: bool = Field(
            default=False,
            description="Capture assistant responses to the brain",
        )
        inject_context: bool = Field(
            default=True,
            description="Search the brain and inject relevant memories into the conversation",
        )
        search_limit: int = Field(
            default=3,
            description="Max number of brain entries to inject as context",
        )
        similarity_threshold: float = Field(
            default=0.3,
            description="Minimum similarity score to include a memory (0.0–1.0)",
        )

    def __init__(self):
        self.type = "filter"
        self.name = "Open Brain"
        self.valves = self.Valves()

    async def on_startup(self):
        print(f"[Open Brain] Filter starting — API: {self.valves.capture_api_url}")

    async def on_shutdown(self):
        print("[Open Brain] Filter shutting down")

    async def _send_to_brain(self, text: str, source: str) -> None:
        """Fire-and-forget capture — don't block the chat flow."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.valves.capture_api_url}/capture",
                    json={"text": text, "source_client": source},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        if result.get("stored"):
                            print(f"[Open Brain] Stored: {result.get('reason', '')[:80]}")
                        else:
                            print(f"[Open Brain] Skipped: {result.get('reason', '')[:80]}")
                    else:
                        print(f"[Open Brain] API error: {resp.status}")
        except Exception as e:
            import traceback
            print(f"[Open Brain] Capture failed (non-fatal): {type(e).__name__}: {e}")
            traceback.print_exc()

    async def _search_brain(self, query: str) -> list:
        """Search the brain for relevant entries."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.valves.capture_api_url}/search",
                    json={"query": query, "limit": self.valves.search_limit},
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        results = data.get("results", [])
                        # Filter by similarity threshold
                        filtered = [
                            r for r in results
                            if r.get("similarity_score", 0) >= self.valves.similarity_threshold
                        ]
                        if filtered:
                            print(f"[Open Brain] Retrieved {len(filtered)} memories (top score: {filtered[0].get('similarity_score', 0):.3f})")
                        return filtered
                    else:
                        print(f"[Open Brain] Search API error: {resp.status}")
                        return []
        except Exception as e:
            print(f"[Open Brain] Search failed (non-fatal): {type(e).__name__}: {e}")
            return []

    def _format_memories(self, results: list) -> str:
        """Format retrieved brain entries into a context block."""
        parts = []
        for r in results:
            entry_type = r.get("entry_type", "unknown")
            topics = ", ".join(r.get("topics", []))
            created = r.get("created_at", "")[:10]  # just the date
            text = r.get("raw_text", "")

            header = f"[{entry_type}]"
            if topics:
                header += f" Topics: {topics}"
            if created:
                header += f" ({created})"

            parts.append(f"{header}\n{text}")

        return "\n\n---\n\n".join(parts)

    async def inlet(self, body: dict, user: Optional[dict] = None) -> dict:
        """Capture the user's message and inject relevant brain context."""
        messages = body.get("messages", [])
        if not messages:
            return body

        last_msg = messages[-1]
        if last_msg.get("role") != "user" or not last_msg.get("content"):
            return body

        content = last_msg["content"]
        if not isinstance(content, str) or len(content.strip()) == 0:
            return body

        # Step 1: Capture the message (fire-and-forget, don't await blocking)
        if self.valves.capture_user_messages:
            await self._send_to_brain(content, "open_webui_user")

        # Step 2: Search the brain for relevant context
        if self.valves.inject_context:
            results = await self._search_brain(content)
            if results:
                context_block = self._format_memories(results)
                context_msg = (
                    "The following memories from the user's Open Brain knowledge base "
                    "may be relevant to this conversation. Use them naturally if they help "
                    "answer the user's question — don't mention them unless the user asks "
                    "about their memories or past context.\n\n"
                    f"{context_block}"
                )

                # Inject as a system message at the start of the conversation
                # If there's already a system message, append to it
                if messages and messages[0].get("role") == "system":
                    messages[0]["content"] += f"\n\n--- Open Brain Context ---\n{context_block}"
                else:
                    messages.insert(0, {
                        "role": "system",
                        "content": context_msg,
                    })

                body["messages"] = messages

        return body

    async def outlet(self, body: dict, user: Optional[dict] = None) -> dict:
        """Optionally capture the assistant's response after it's complete."""
        if not self.valves.capture_assistant_responses:
            return body

        messages = body.get("messages", [])
        if not messages:
            return body

        # Find the last assistant message
        for msg in reversed(messages):
            if msg.get("role") == "assistant" and msg.get("content"):
                content = msg["content"]
                if isinstance(content, str) and len(content.strip()) > 0:
                    await self._send_to_brain(content, "open_webui_assistant")
                break

        return body
