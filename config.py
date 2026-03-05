"""Central configuration — reads from .env, never hardcodes values."""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root
_env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(_env_path)


def _get(key: str, default: str | None = None) -> str:
    value = os.getenv(key, default)
    if value is None:
        raise RuntimeError(f"Missing required env var: {key}")
    return value


# -- Database --
POSTGRES_HOST = _get("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(_get("POSTGRES_PORT", "5433"))
POSTGRES_DB = _get("POSTGRES_DB", "open_brain")
POSTGRES_USER = _get("POSTGRES_USER", "brain_user")
POSTGRES_PASSWORD = _get("POSTGRES_PASSWORD", "changeme")

DATABASE_URL = (
    f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
    f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
)

# -- Ollama --
OLLAMA_BASE_URL = _get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_EMBEDDING_MODEL = _get("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")
OLLAMA_CLASSIFIER_MODEL = _get("OLLAMA_CLASSIFIER_MODEL", "llama3.1:8b")
OLLAMA_EXTRACTOR_MODEL = _get("OLLAMA_EXTRACTOR_MODEL", "llama3.1:8b")

# -- MCP Server --
MCP_SERVER_NAME = _get("MCP_SERVER_NAME", "open-brain")
MCP_AUTH_TOKEN = _get("MCP_AUTH_TOKEN", "changeme")

# -- Token Budget --
MONTHLY_TOKEN_BUDGET = float(_get("MONTHLY_TOKEN_BUDGET", "10.0"))

# Per-model cost rates (per 1k tokens).  Ollama is free; add cloud rates here.
# Format: {"provider/model": {"prompt_per_1k": X, "completion_per_1k": Y}}
import json as _json

_raw_costs = os.getenv("TOKEN_COSTS", "{}")
try:
    TOKEN_COSTS: dict = _json.loads(_raw_costs)
except Exception:
    TOKEN_COSTS = {}

# -- Optional tunnel --
TUNNEL_AUTH_TOKEN = os.getenv("TUNNEL_AUTH_TOKEN", "")
