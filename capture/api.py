"""HTTP API for the capture pipeline — used by Open WebUI Pipeline filter."""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI
from pydantic import BaseModel

from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

import config  # noqa: E402
from capture.pipeline import capture  # noqa: E402
from capture.token_tracker import get_stats as get_token_stats, log_usage  # noqa: E402
from db_client.client import close_pool  # noqa: E402
from mcp_server.tools.search import search_brain  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("capture-api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Capture API starting")
    yield
    await close_pool()
    logger.info("Capture API shutdown")


app = FastAPI(title="Open Brain Capture API", lifespan=lifespan)


class CaptureRequest(BaseModel):
    text: str
    source_client: str = "open_webui"


class SearchRequest(BaseModel):
    query: str
    limit: int = 5


@app.post("/capture")
async def capture_endpoint(req: CaptureRequest):
    """Capture text into the brain."""
    result = await capture(text=req.text, source_client=req.source_client)
    return result


@app.post("/search")
async def search_endpoint(req: SearchRequest):
    """Quick semantic search — used to inject context into conversations."""
    result = await search_brain(query=req.query, limit=req.limit)
    return result


# ── Token tracking endpoints ──────────────────────────────────────────

class TokenUsageRequest(BaseModel):
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int = 0
    operation: str = "chat"


@app.post("/token-usage")
async def token_usage_endpoint(req: TokenUsageRequest):
    """Accept explicit token logs from external callers."""
    await log_usage(
        provider=req.provider,
        model=req.model,
        prompt_tokens=req.prompt_tokens,
        completion_tokens=req.completion_tokens,
        operation=req.operation,
    )
    return {"status": "logged"}


@app.get("/api/token-stats")
async def token_stats_endpoint(days: int = 30):
    """Return token usage stats as JSON."""
    return await get_token_stats(days=days)


# ── Dashboard ─────────────────────────────────────────────────────────

_static_dir = Path(__file__).resolve().parent / "static"


@app.get("/dashboard")
async def dashboard():
    """Serve the token usage dashboard."""
    html_file = _static_dir / "dashboard.html"
    if not html_file.exists():
        return HTMLResponse("<h1>Dashboard not built yet</h1>", status_code=404)
    return HTMLResponse(html_file.read_text(encoding="utf-8"))


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8100)
