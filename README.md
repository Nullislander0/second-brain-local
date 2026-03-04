The following is mostly AI directions written by my agent thinking everyone will work the same way I did. They won't. So there's a lot of assumptions being made here. I'll come in with *edit - not really, etc. to try and right the ship as I can.*

# Open Brain

A local "second brain" that passively captures, classifies, embeds, and stores context from AI interactions, then exposes that memory through a chat interface (Open WebUI) and MCP tools for Claude Code. *It's also supposed to be discoverable and searchable by claude code and able to be linked to that automatically on startup. I mean you could just ask claude code to spin up a project and do that, but I'd like to have some instructions for the casuals, too. This is the real utility of this tool IMHO: to be able to have your agents search relevant data from your ever-evolving memory database.*

Everything runs on your local workstation. No cloud services required (though you can optionally connect external APIs for premium chat models).

## Architecture Overview

```
┌─────────────────┐     ┌──────────────┐     ┌──────────────────┐
│   Open WebUI    │────▶│   Pipeline   │────▶│   Capture API    │
│  localhost:3000 │     │    Filter    │     │  localhost:8100   │
│  (chat with AI) │     │  (auto-hook) │     │                  │
└─────────────────┘     └──────────────┘     └────────┬─────────┘
                                                      │
                              ┌────────────────────────┼────────────────┐
                              ▼                        ▼                ▼
                        ┌───────────┐          ┌─────────────┐   ┌──────────┐
                        │  Ollama   │          │  PostgreSQL  │   │  Ollama  │
                        │ Classifier│          │  + pgvector  │   │ Embedder │
                        │ qwen3:8b  │          │  port 5433   │   │mxbai-emb │
                        └───────────┘          └──────┬───────┘   └──────────┘
                                                      │
                              ┌────────────────────────┼────────────────┐
                              ▼                        ▼                ▼
                        ┌───────────┐          ┌─────────────┐   ┌──────────┐
                        │ MCP Server│          │ Brain Search │   │ Context  │
                        │(Claude Code)│        │  (semantic)  │   │Injection │
                        │ 4 tools   │          │              │   │(into chat)│
                        └───────────┘          └──────────────┘   └──────────┘
```

**Data flow:** You chat → pipeline filter captures your message → classifier decides if it's worth storing → metadata extractor + embedder run concurrently → stored in PostgreSQL → searchable via MCP tools or auto-injected into future chat context.

## Prerequisites

- **Python 3.11+**
- **Docker Desktop** (or Docker Engine)
- **Ollama** — [Install from ollama.com](https://ollama.com)

## First-Time Setup

### 1. Clone and configure

```bash
git clone https://github.com/YOUR_USERNAME/open-brain.git
cd open-brain
cp .env.example .env
cp docker/.env.example docker/.env
```

Edit `.env` and `docker/.env` to set your preferred models, database password, and optional API keys.

### 2. Pull Ollama models
*So you don't need these ones, gpt-oss:20b is kinda bad at this even if it's great at chat, IMHO, but really just use a good, fast one (like qwen3:8b and a small task one like mxbai-embed-large - all others are just if you want to chat with the WebUI window about what it's recorded about you*
```bash
# Embedding model (1024 dimensions)
ollama pull mxbai-embed-large

# Classifier and extractor model
ollama pull qwen3:8b
```

### 3. Start the full stack
*Firstly I think you need to make sure Ollama is up - so run that and that will make it available to consume. Pretty sure you could reconfigure this to work with other local LLM hosting tools, too, but this is the way I'm using it now - subject to change*
```bash
cd docker
docker compose up -d
```
*Or just open docker from the search bar - it will do what it needs to do once configured*
This starts four services:

| Service | Container | Port | Purpose |
|---------|-----------|------|---------|
| PostgreSQL + pgvector | `open_brain_db` | 5433 | Vector storage and search |
| Open WebUI | `open_brain_webui` | 3000 | Chat interface |
| Pipelines | `open_brain_pipelines` | 9099 | Message capture filter |
| Capture API | `open_brain_capture` | 8100 | Classification, extraction, embedding |

Verify everything is healthy:

```bash
docker compose ps
```

### 4. Install Python dependencies (for MCP server and local development)
*Maybe do this before you startup the whole stack... thinking my agent messed this up, but whatever...*
```bash
pip install -r requirements.txt
```

### 5. Open the chat interface

Go to **http://localhost:3000** and create your account. This is a local-only account, *so you can put whatever you want in the login* — Open WebUI runs entirely on your machine.

## How It Works

### Passive Capture

Every message you send in Open WebUI is automatically intercepted by the pipeline filter. You don't need to do anything special — just chat naturally. The system:

1. **Classifies** the text — only substantive content is stored (decisions, observations, action items, references, project notes). Chit-chat, greetings, and system noise are filtered out.
2. **Extracts metadata** — entry type, topics, people, projects, action items
3. **Generates embeddings** — 1024-dim vectors via mxbai-embed-large for semantic search
4. **Detects duplicates** — skips near-identical entries (cosine similarity > 0.98)

### Context Injection

When you send a message, the filter also searches the brain for relevant memories and injects them into the conversation context. The LLM sees your past decisions and knowledge without you having to remind it.

### What Gets Stored vs. Filtered

| Stored | Filtered |
|--------|----------|
| "I decided to use Redis for caching because..." | "hello" |
| "The deployment is scheduled for Friday" | "thanks!" |
| "We chose Rust over Go for performance reasons" | "ok sounds good" |
| "TODO: update the API docs before release" | "what time is it?" |

## Connecting Premium Models (Optional)

Open WebUI supports external APIs alongside local Ollama models. To add an OpenAI-compatible API (NVIDIA, OpenAI, etc.):

1. Add your API key to `docker/.env`:
   ```bash
   NVIDIA_API_KEY=nvapi-your-key-here
   ```

2. The docker-compose.yml already configures the NVIDIA endpoint. For other providers, edit the `OPENAI_API_BASE_URLS` and `OPENAI_API_KEYS` environment variables (semicolon-separated for multiple).

3. Restart Open WebUI:
   ```bash
   cd docker && docker compose up -d open-webui
   ```

Premium models appear in the model dropdown alongside your local Ollama models.

## Claude Code Integration

Open Brain exposes four MCP tools that Claude Code can use from any project directory:

| Tool | Purpose |
|------|---------|
| `capture_text_tool` | Store an entry into the brain |
| `search_brain_tool` | Semantic search over memories |
| `recent_entries` | Browse recent entries by time or type |
| `brain_stats` | Entry counts, top topics, storage overview |

### Global setup (all projects)

Add the MCP server to `~/.claude.json` (replace the path with where you cloned this repo):

```json
{
  "mcpServers": {
    "open-brain": {
      "command": "python",
      "args": ["/path/to/open-brain/mcp_server/server.py"],
      "scope": "user"
    }
  }
}
```

Or add a `.mcp.json` to any project root for project-level access:

```json
{
  "mcpServers": {
    "open-brain": {
      "command": "python",
      "args": ["/path/to/open-brain/mcp_server/server.py"]
    }
  }
}
```

### Status line

A status line indicator shows brain status at the bottom of every Claude Code session:

- 🧠 **Brain online** (green) — Docker + Ollama both running
- 🧠 **Ollama not running** (yellow) — containers up but no LLM
- 🧠 **Docker not running** (yellow) — Ollama up but no database
- 🧠 **Brain offline** (red) — both down
*The emojis don't display in the terminal, FYI - not yet anyway, but LMK if you fix it somehow. The other parts do work, however*
Configured in `~/.claude/settings.json` and `~/.claude/statusline.sh`.

## Capture Pipeline (Programmatic)

To store text from your own code:

```python
from capture.pipeline import capture

result = await capture(
    "We decided to use Rust for the CLI because...",
    source_client="my_app"
)
# {"stored": True, "id": "uuid-here", "reason": "Stored as decision (confidence 0.95)"}
```

## Model Configuration

All models are configured via environment variables in `.env`:

```bash
OLLAMA_EMBEDDING_MODEL=mxbai-embed-large
OLLAMA_CLASSIFIER_MODEL=qwen3:8b
OLLAMA_EXTRACTOR_MODEL=qwen3:8b
```

### Embedding Models

| Model | Dimensions | Size | Notes |
|-------|-----------|------|-------|
| `mxbai-embed-large` | 1024 | 669 MB | Best quality, recommended |
| `nomic-embed-text` | 768 | 274 MB | Lighter alternative (requires schema change) |

### Classifier / Extractor Models

| Model | Size | Notes |
|-------|------|-------|
| `qwen3:8b` | 5.2 GB | Good balance of speed and accuracy |
| `llama3.1:8b` | 4.7 GB | Solid alternative |
| `mistral:7b` | 4.1 GB | Fastest of the three |

If you change the embedding model to one with a different dimension, you must update `db/schema.sql` (change `vector(1024)`) and recreate the database volume — this deletes all stored entries.

## Project Structure

```
open-brain/
├── docker/
│   ├── docker-compose.yml        # Full stack: DB, WebUI, Pipelines, Capture API
│   ├── Dockerfile.capture        # Capture API container image
│   └── .env                      # Docker-specific secrets (API keys)
├── db/
│   └── schema.sql                # PostgreSQL schema + pgvector indexes
├── capture/
│   ├── pipeline.py               # Main capture pipeline
│   ├── classifier.py             # Relevance gate (qwen3:8b)
│   ├── extractor.py              # Metadata extraction
│   ├── embedder.py               # Embedding generation (mxbai-embed-large)
│   ├── api.py                    # FastAPI HTTP wrapper (runs in container)
│   └── prompts.py                # Ollama prompt templates
├── mcp_server/
│   ├── server.py                 # MCP stdio server (4 tools)
│   └── tools/
│       ├── capture.py            # capture_text_tool
│       ├── search.py             # search_brain_tool
│       ├── recent.py             # recent_entries
│       └── stats.py              # brain_stats
├── db_client/
│   └── client.py                 # Async PostgreSQL client (asyncpg + pgvector)
├── pipelines/
│   └── open_brain_filter.py      # Open WebUI pipeline filter (capture + retrieval)
├── scripts/
│   ├── seed_knowledge.py         # Seed brain with foundational knowledge
│   └── seed_direct.py            # Direct DB seeding (bypasses classifier)
├── docs/
│   └── system_prompt.md          # System prompt for Open WebUI
├── tests/                        # Full test suite
├── .env                          # Local development config
├── .env.example
├── .mcp.json                     # Project-level MCP config
├── config.py                     # Central configuration
└── requirements.txt
```

## Daily Usage

1. **Start Docker Desktop** — all containers auto-start
2. **Start Ollama** — needed for classification, embedding, and local chat
3. **Chat at localhost:3000** — your messages are passively captured
4. **Use Claude Code anywhere** — brain tools available via MCP, status line shows connection

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Brain tools fail with connection error | Start Docker Desktop and Ollama |
| Capture API returns embedding errors | Ollama isn't running — start it |
| Chat models don't appear in Open WebUI | Check Ollama is running; restart Open WebUI container |
| Pipeline filter not loading | Run `docker compose restart pipelines` |
| NVIDIA models not showing | Check `NVIDIA_API_KEY` in `docker/.env`; restart Open WebUI |
