"""Test metadata extractor against live Ollama with varied input."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from capture.extractor import ExtractionResult, extract_metadata

VALID_ENTRY_TYPES = {"observation", "decision", "action_item", "reference", "project_note"}

TEST_CASES = [
    {
        "text": (
            "We decided to use PostgreSQL with pgvector for the Open Brain project "
            "because it gives us cosine similarity search without a separate vector "
            "database. Sarah recommended it after evaluating Qdrant and Pinecone."
        ),
        "expected_type": "decision",
        "expect_topics": True,
        "expect_people": True,
        "expect_projects": True,
        "description": "Decision with people and project",
    },
    {
        "text": (
            "TODO: Set up the CI/CD pipeline for the dashboard project by Friday. "
            "Also need to write unit tests for the auth module. "
            "Assign the deployment task to Marcus."
        ),
        "expected_type": "action_item",
        "expect_topics": True,
        "expect_people": True,
        "expect_projects": True,
        "expect_action_items": True,
        "description": "Action items with people and deadlines",
    },
    {
        "text": (
            "Python's asyncio event loop runs in a single thread. To do CPU-bound "
            "work without blocking, use ProcessPoolExecutor. For I/O-bound work, "
            "the default ThreadPoolExecutor is sufficient."
        ),
        "expected_type": "reference",
        "expect_topics": True,
        "expect_people": False,
        "expect_projects": False,
        "description": "Technical reference with no people/projects",
    },
    {
        "text": (
            "Noticed that the API response times for the Acme project have been "
            "increasing over the past week. Average latency went from 120ms to 450ms. "
            "Might be related to the new caching layer."
        ),
        "expected_type": "observation",
        "expect_topics": True,
        "expect_projects": True,
        "description": "Performance observation with project",
    },
    {
        "text": (
            "Meeting notes from the Open Brain sync: agreed on using MCP for the "
            "server protocol. Jake will handle the Docker setup, Lisa owns the "
            "capture pipeline. Next sync is Thursday."
        ),
        "expected_type": "project_note",
        "expect_topics": True,
        "expect_people": True,
        "expect_projects": True,
        "description": "Project meeting notes",
    },
]


async def main() -> None:
    passed = 0
    failed = 0

    for case in TEST_CASES:
        result = await extract_metadata(case["text"])
        desc = case["description"]
        errors = []

        # Required fields are always present
        if not isinstance(result, ExtractionResult):
            errors.append(f"Wrong return type: {type(result)}")
        if result.entry_type not in VALID_ENTRY_TYPES:
            errors.append(f"Invalid entry_type: {result.entry_type}")
        if not isinstance(result.topics, list):
            errors.append(f"topics is not a list: {type(result.topics)}")
        if not isinstance(result.people, list):
            errors.append(f"people is not a list: {type(result.people)}")
        if not isinstance(result.projects, list):
            errors.append(f"projects is not a list: {type(result.projects)}")
        if not isinstance(result.action_items, list):
            errors.append(f"action_items is not a list: {type(result.action_items)}")

        # Check entry_type matches expected (soft — LLM may differ)
        type_match = result.entry_type == case["expected_type"]

        # Check that non-empty arrays are present when expected
        if case.get("expect_topics") and not result.topics:
            errors.append("Expected topics but got empty list")
        if case.get("expect_people") and not result.people:
            errors.append("Expected people but got empty list")
        if case.get("expect_projects") and not result.projects:
            errors.append("Expected projects but got empty list")
        if case.get("expect_action_items") and not result.action_items:
            errors.append("Expected action_items but got empty list")
        if case.get("expect_people") is False and result.people:
            errors.append(f"Expected no people but got {result.people}")
        if case.get("expect_projects") is False and result.projects:
            errors.append(f"Expected no projects but got {result.projects}")

        ok = len(errors) == 0
        status = "PASS" if ok else "FAIL"
        if ok:
            passed += 1
        else:
            failed += 1

        type_tag = "match" if type_match else f"expected {case['expected_type']}"
        print(
            f"  [{status}] {desc}\n"
            f"         type={result.entry_type} ({type_tag})\n"
            f"         topics={result.topics}\n"
            f"         people={result.people}\n"
            f"         projects={result.projects}\n"
            f"         action_items={result.action_items}"
        )
        if errors:
            for e in errors:
                print(f"         ERROR: {e}")

    print(f"\nResults: {passed} passed, {failed} failed out of {len(TEST_CASES)}")
    if failed == 0:
        print("All extractor tests passed!")


if __name__ == "__main__":
    asyncio.run(main())
