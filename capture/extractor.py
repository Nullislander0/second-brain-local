"""Metadata extraction — pulls structured fields from text via Ollama."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field

import httpx

import config
from capture.prompts import METADATA_EXTRACTION_PROMPT

logger = logging.getLogger(__name__)

VALID_ENTRY_TYPES = frozenset({
    "observation", "decision", "action_item", "reference", "project_note",
})

_MAX_RETRIES = 3
_BASE_TIMEOUT = 60.0


@dataclass
class ExtractionResult:
    entry_type: str
    topics: list[str] = field(default_factory=list)
    people: list[str] = field(default_factory=list)
    projects: list[str] = field(default_factory=list)
    action_items: list[str] = field(default_factory=list)


def _parse_response(raw: str) -> dict:
    """Extract JSON from LLM output, tolerating markdown fences and preamble."""
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if m:
        return json.loads(m.group(1))
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        return json.loads(m.group(0))
    raise ValueError(f"No JSON found in extractor response: {raw!r}")


def _to_str_list(val) -> list[str]:
    """Coerce a value to a list of non-empty strings."""
    if not isinstance(val, list):
        return []
    return [str(v).strip() for v in val if v and str(v).strip()]


def _build_result(parsed: dict) -> ExtractionResult:
    """Validate and normalise parsed JSON into an ExtractionResult."""
    entry_type = str(parsed.get("entry_type", "observation")).lower().strip()
    if entry_type not in VALID_ENTRY_TYPES:
        logger.warning("Unknown entry_type %r, defaulting to 'observation'", entry_type)
        entry_type = "observation"

    return ExtractionResult(
        entry_type=entry_type,
        topics=_to_str_list(parsed.get("topics")),
        people=_to_str_list(parsed.get("people")),
        projects=_to_str_list(parsed.get("projects")),
        action_items=_to_str_list(parsed.get("action_items")),
    )


async def extract_metadata(text: str) -> ExtractionResult:
    """Extract structured metadata from text via Ollama.

    Retries up to 3 times with exponential backoff.
    On total failure returns a minimal ExtractionResult so the pipeline
    can still store the entry.
    """
    prompt = METADATA_EXTRACTION_PROMPT.format(text=text)
    url = f"{config.OLLAMA_BASE_URL}/api/generate"
    payload = {
        "model": config.OLLAMA_EXTRACTOR_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.1},
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
                model=config.OLLAMA_EXTRACTOR_MODEL,
                prompt_tokens=data.get("prompt_eval_count", 0),
                completion_tokens=data.get("eval_count", 0),
                operation="extract",
            )

            raw_response = data.get("response", "")
            parsed = _parse_response(raw_response)
            result = _build_result(parsed)

            logger.debug(
                "Extraction: type=%s topics=%s attempt=%d",
                result.entry_type,
                result.topics,
                attempt,
            )
            return result

        except (httpx.HTTPError, httpx.TimeoutException, ValueError, KeyError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt < _MAX_RETRIES:
                wait = 2 ** (attempt - 1)
                logger.warning(
                    "Extractor attempt %d/%d failed (%s), retrying in %ds...",
                    attempt,
                    _MAX_RETRIES,
                    exc,
                    wait,
                )
                await asyncio.sleep(wait)
            else:
                logger.error(
                    "Extractor failed after %d attempts: %s", _MAX_RETRIES, exc
                )

    # Fail-safe: return minimal metadata so the entry can still be stored
    logger.warning("Extractor unavailable, returning default metadata")
    return ExtractionResult(entry_type="observation")
