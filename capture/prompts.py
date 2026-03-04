"""Ollama prompt templates — edit here without touching logic code."""

RELEVANCE_GATE_PROMPT = """\
You are a classifier for a personal knowledge base. Given a piece of text from an AI conversation, classify it.

Text: {text}

Respond with JSON only:
{{
  "label": "store|too_short|chit_chat|system_noise|uncertain",
  "confidence": 0.0-1.0,
  "reason": "one sentence"
}}"""

METADATA_EXTRACTION_PROMPT = """\
Extract structured metadata from this text for a personal knowledge base.

Text: {text}

Respond with JSON only:
{{
  "entry_type": "observation|decision|action_item|reference|project_note",
  "topics": ["topic1", "topic2"],
  "people": ["name1"],
  "projects": ["project_name"],
  "action_items": ["item1"]
}}

Use empty arrays if nothing applies. Be concise with tags."""
