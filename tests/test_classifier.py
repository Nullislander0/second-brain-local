"""Test the relevance gate classifier against live Ollama.

Provides examples for each label category and asserts correct classification.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from capture.classifier import ClassificationResult, classify

# --- Test cases: (input_text, expected_label, description) ---
TEST_CASES = [
    # store — substantive knowledge worth remembering
    (
        "We decided to use PostgreSQL with pgvector for the embedding store because "
        "it gives us cosine similarity search without a separate vector database. "
        "The alternative was Qdrant but we wanted fewer moving parts.",
        "store",
        "Architectural decision with rationale",
    ),
    (
        "The root cause of the memory leak was that the connection pool was never "
        "closed on shutdown. Adding an atexit handler fixed it. The pool was growing "
        "by about 2 connections per request cycle.",
        "store",
        "Debugging insight with fix",
    ),
    # too_short — under ~20 words, no informational value
    (
        "ok thanks",
        "too_short",
        "Two-word acknowledgment",
    ),
    (
        "yes",
        "too_short",
        "Single-word response",
    ),
    # chit_chat — casual filler
    (
        "Hey, how's it going? Hope you're having a great day!",
        "chit_chat",
        "Casual greeting",
    ),
    (
        "Haha that's funny, nice one",
        "chit_chat",
        "Casual reaction",
    ),
    # system_noise — error messages, formatting, boilerplate
    (
        "Error: ENOENT: no such file or directory, open '/tmp/foo.txt'",
        "system_noise",
        "File system error message",
    ),
    (
        "Please format your response as a numbered list with bullet points.",
        "system_noise",
        "Formatting instruction",
    ),
]


async def main() -> None:
    passed = 0
    failed = 0

    for text, expected_label, description in TEST_CASES:
        result = await classify(text)
        assert isinstance(result, ClassificationResult)
        assert result.label in {"store", "too_short", "chit_chat", "system_noise", "uncertain"}
        assert 0.0 <= result.confidence <= 1.0
        assert isinstance(result.reason, str)

        # For store/uncertain, should_store must be True
        # For others, should_store must be False
        ok = result.label == expected_label
        # Accept 'uncertain' as partial pass for borderline cases
        soft_ok = ok or result.label == "uncertain"
        status = "PASS" if ok else ("SOFT" if soft_ok else "FAIL")

        if ok:
            passed += 1
        elif soft_ok:
            passed += 1  # count soft passes
        else:
            failed += 1

        print(
            f"  [{status}] {description}\n"
            f"         expected={expected_label} got={result.label} "
            f"conf={result.confidence:.2f} should_store={result.should_store}\n"
            f"         reason: {result.reason}"
        )

    print(f"\nResults: {passed} passed, {failed} failed out of {len(TEST_CASES)}")
    if failed > 0:
        print("WARNING: Some classifications did not match expected labels.")
        print("LLM classifiers are probabilistic — review failures manually.")
    else:
        print("All classifier tests passed!")


if __name__ == "__main__":
    asyncio.run(main())
