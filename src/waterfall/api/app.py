"""FastAPI application."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from waterfall.api.schemas import ParamsIn, RenderStateOut
from waterfall.api.stream import run_session
from waterfall.domain.state import render_state

app = FastAPI(title="Waterfall", version="0.1.0")


@app.get("/health")
def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


@app.post("/render")
def render_once(params: ParamsIn) -> RenderStateOut:
    """One-shot render with no smoothing.

    Exists for tests and tooling: the contract fixtures that pin the browser
    against Python are generated through this path.
    """
    return RenderStateOut.from_domain(render_state(params.to_domain()))


@app.websocket("/ws")
async def stream(websocket: WebSocket) -> None:
    await run_session(websocket)


_WEB_DIST = Path(__file__).resolve().parents[3] / "web" / "dist"
if _WEB_DIST.is_dir():
    app.mount("/", StaticFiles(directory=_WEB_DIST, html=True), name="web")
