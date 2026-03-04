"""Relevance gate — classifies text before it enters the capture pipeline."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass

import httpx

import config
from capture.prompts import RELEVANCE_GATE_PROMPT

logger = logging.getLogger(__name__)

VALID_LABELS = frozenset({"store", "too_short", "chit_chat", "system_noise", "uncertain"})
STORE_LABELS = frozenset({"store", "uncertain"})

_MAX_RETRIES = 3
_BASE_TIMEOUT = 60.0  # seconds — LLM generation is slower than embeddings


@dataclass
class ClassificationResult:
    label: str
    confidence: float
    reason: str
    should_store: bool


def _parse_response(raw: str) -> dict:
    """Extract JSON from LLM output, tolerating markdown fences and preamble."""
    # Try to find a JSON block in markdown fences first
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if m:
        return json.loads(m.group(1))
    # Otherwise find the first { ... } block
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        return json.loads(m.group(0))
    raise ValueError(f"No JSON found in classifier response: {raw!r}")


async def classify(text: str) -> ClassificationResult:
    """Classify text through the relevance gate.

    Returns a ClassificationResult with should_store=True when the
    label is 'store' or 'uncertain'.

    Retries up to 3 times with exponential backoff.
    On total failure, defaults to 'uncertain' (store the entry) so data
    is not silently lost.
    """
    prompt = RELEVANCE_GATE_PROMPT.format(text=text)
    url = f"{config.OLLAMA_BASE_URL}/api/generate"
    payload = {
        "model": config.OLLAMA_CLASSIFIER_MODEL,
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
                model=config.OLLAMA_CLASSIFIER_MODEL,
                prompt_tokens=data.get("prompt_eval_count", 0),
                completion_tokens=data.get("eval_count", 0),
                operation="classify",
            )

            raw_response = data.get("response", "")
            parsed = _parse_response(raw_response)

            label = parsed.get("label", "uncertain").lower().strip()
            if label not in VALID_LABELS:
                logger.warning("Unknown label %r, defaulting to 'uncertain'", label)
                label = "uncertain"

            confidence = float(parsed.get("confidence", 0.5))
            confidence = max(0.0, min(1.0, confidence))
            reason = str(parsed.get("reason", ""))

            result = ClassificationResult(
                label=label,
                confidence=confidence,
                reason=reason,
                should_store=label in STORE_LABELS,
            )
            logger.debug(
                "Classification: label=%s confidence=%.2f attempt=%d",
                result.label,
                result.confidence,
                attempt,
            )
            return result

        except (httpx.HTTPError, httpx.TimeoutException, ValueError, KeyError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt < _MAX_RETRIES:
                wait = 2 ** (attempt - 1)
                logger.warning(
                    "Classifier attempt %d/%d failed (%s), retrying in %ds...",
                    attempt,
                    _MAX_RETRIES,
                    exc,
                    wait,
                )
                await asyncio.sleep(wait)
            else:
                logger.error(
                    "Classifier failed after %d attempts: %s", _MAX_RETRIES, exc
                )

    # Fail-open: default to storing so data is not silently lost
    logger.warning("Classifier unavailable, defaulting to 'uncertain' (will store)")
    return ClassificationResult(
        label="uncertain",
        confidence=0.0,
        reason=f"Classifier unavailable: {last_error}",
        should_store=True,
    )
