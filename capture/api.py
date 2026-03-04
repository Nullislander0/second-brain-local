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

import config  # noqa: E402
from capture.pipeline import capture  # noqa: E402
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


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8100)
