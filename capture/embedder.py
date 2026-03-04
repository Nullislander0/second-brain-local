"""Ollama embedding generation with timeout and retry logic."""

from __future__ import annotations

import asyncio
import logging

import httpx

import config

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_BASE_TIMEOUT = 30.0  # seconds


async def generate_embedding(text: str) -> list[float]:
    """Call Ollama embedding endpoint and return the vector.

    Retries up to 3 times with exponential backoff.
    Raises RuntimeError if all attempts fail.
    """
    url = f"{config.OLLAMA_BASE_URL}/api/embed"
    payload = {
        "model": config.OLLAMA_EMBEDDING_MODEL,
        "input": text,
    }

    last_error: Exception | None = None

    for attempt in range(1, _MAX_RETRIES + 1):
        timeout = _BASE_TIMEOUT * attempt
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()

            # Track token usage (fire-and-forget)
            from capture.token_tracker import log_usage
            await log_usage(
                provider="ollama",
                model=config.OLLAMA_EMBEDDING_MODEL,
                prompt_tokens=data.get("prompt_eval_count", 0),
                completion_tokens=0,
                operation="embed",
            )

            embeddings = data.get("embeddings")
            if not embeddings or not embeddings[0]:
                raise ValueError(f"Empty embeddings in Ollama response: {data}")

            vector = embeddings[0]
            logger.debug(
                "Embedding generated: model=%s dim=%d attempt=%d",
                config.OLLAMA_EMBEDDING_MODEL,
                len(vector),
                attempt,
            )
            return vector

        except (httpx.HTTPError, httpx.TimeoutException, ValueError, KeyError) as exc:
            last_error = exc
            if attempt < _MAX_RETRIES:
                wait = 2 ** (attempt - 1)
                logger.warning(
                    "Embedding attempt %d/%d failed (%s), retrying in %ds...",
                    attempt,
                    _MAX_RETRIES,
                    exc,
                    wait,
                )
                await asyncio.sleep(wait)
            else:
                logger.error(
                    "Embedding failed after %d attempts: %s", _MAX_RETRIES, exc
                )

    raise RuntimeError(
        f"Ollama embedding failed after {_MAX_RETRIES} attempts: {last_error}"
    )
