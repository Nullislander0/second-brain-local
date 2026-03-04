# CLAUDE.md — Open Brain

## What This Is

Local "second brain" system. Captures text from chat (Open WebUI) or MCP tools, classifies it for relevance, extracts metadata, generates vector embeddings, and stores everything in PostgreSQL+pgvector for semantic search.

## Quick Start

```bash
cp .env.example .env
cp docker/.env.example docker/.env
# Edit both .env files with your settings
cd docker && docker compose up -d
pip install -r requirements.txt
```

**Prerequisites:** Docker Desktop, Ollama (with `mxbai-embed-large` and `qwen3:8b` pulled), Python 3.11+.

## Architecture

```
User message → Pipeline Filter → Classifier (qwen3:8b) → [reject junk]
                                                        → Extractor (qwen3:8b) + Embedder (mxbai-embed-large) [concurrent]
                                                        → Duplicate check (cosine > 0.98)
                                                        → Store in PostgreSQL+pgvector
```

### Services (docker-compose)

| Service | Port | Container |
|---------|------|-----------|
| PostgreSQL+pgvector | **5433** (not 5432) | open_brain_db |
| Open WebUI | 3000 | open_brain_webui |
| Pipelines | 9099 | open_brain_pipelines |
| Capture API | 8100 | open_brain_capture |

**Important:** PostgreSQL runs on port **5433** to avoid conflicts with local PG installs.

## Key Modules

- `capture/pipeline.py` — Main pipeline orchestrator: classify → extract + embed → dedupe → store
- `capture/classifier.py` — Relevance gate using Ollama (qwen3:8b)
- `capture/extractor.py` — Metadata extraction: entry_type, topics, people, projects, action_items
- `capture/embedder.py` — Vector embedding via Ollama (mxbai-embed-large, 1024 dimensions)
- `capture/api.py` — FastAPI HTTP wrapper for the capture pipeline (runs in Docker)
- `db_client/client.py` — Async PostgreSQL client (asyncpg + pgvector)
- `mcp_server/server.py` — MCP stdio server exposing 4 tools (FastMCP, MCP SDK v1.26.0)
- `mcp_server/tools/` — Individual tool implementations: capture, search, recent, stats
- `pipelines/open_brain_filter.py` — Open WebUI pipeline filter (passive capture + context injection)
- `config.py` — Central config, reads all values from `.env`, never hardcode values

## Conventions

- **All I/O is async** — use `async/await` with `asyncpg`, `httpx`, `asyncio.create_task` for concurrency
- **Config from env vars only** — everything goes through `config.py` which reads `.env`. Never hardcode connection strings, model names, or ports
- **Embedding dimension is 1024** — matches mxbai-embed-large. Changing the model requires updating `db/schema.sql` and recreating the DB volume
- **Entry types:** observation, decision, action_item, reference, project_note
- **Ollama models are called via httpx** — POST to `{OLLAMA_BASE_URL}/api/generate` (chat) or `/api/embed` (embeddings)
- **Prompt templates live in `capture/prompts.py`** — keep them there, not inline

## Running Tests

```bash
pytest tests/
```

Tests use pytest-asyncio. The test suite covers classifier, embedder, extractor, DB client, pipeline, MCP tools, and integration.

## Database Schema

Defined in `db/schema.sql`. Key table is `brain_entries`:
- `id` (UUID), `raw_text`, `embedding` (vector(1024)), `entry_type`, `topics` (text[]), `people` (text[]), `projects` (text[]), `action_items` (text[]), `source_client`, `relevance_score`, `created_at`
- Indexes: ivfflat on embeddings, GIN on array columns, btree on created_at

Token usage tracking in `db/02_token_usage.sql`.

## File Layout

```
├── capture/          # Classify → extract → embed → store pipeline
├── db/               # SQL schema and migrations
├── db_client/        # Async PostgreSQL client
├── docker/           # docker-compose.yml, Dockerfile, .env.example
├── docs/             # System prompts for Open WebUI
├── mcp_server/       # MCP stdio server + tools
├── pipelines/        # Open WebUI pipeline filter
├── scripts/          # Seed scripts (seed_knowledge.py, seed_direct.py)
├── tests/            # Full test suite
├── config.py         # Central env-based configuration
└── requirements.txt  # Python dependencies
```
