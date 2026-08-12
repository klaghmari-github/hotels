"""
API + UI console web de gestion (file d'attente features/anomalies).

Separation stricte: ne importe pas renatus produit.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from queue_store import QueueStore

STATIC = Path(__file__).resolve().parent / "static"
store = QueueStore(
    Path(os.environ["GESTION_DIR"])
    if os.environ.get("GESTION_DIR")
    else None
)

app = FastAPI(title="Renatus Gestion Web Console", version="1.0.0")


class MessageIn(BaseModel):
    text: str = Field(..., min_length=1)
    kind: str = Field(default="auto")  # feature|anomaly|question|auto
    parallel_ok: bool = True


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "service": "gestion-web-console"}


@app.get("/api/status")
def api_status() -> dict:
    return store.get_status()


@app.get("/api/messages")
def api_messages(limit: int = 200) -> dict:
    return {"messages": store.list_messages(limit=limit)}


@app.get("/api/queue")
def api_queue() -> dict:
    return {"queue": store.list_queue()}


@app.post("/api/messages")
def api_post_message(body: MessageIn) -> dict:
    try:
        return store.add_user_message(
            body.text,
            kind=body.kind,
            parallel_ok=body.parallel_ok,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/", response_class=HTMLResponse)
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


if STATIC.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")
