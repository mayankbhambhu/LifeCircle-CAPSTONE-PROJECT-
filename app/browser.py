"""Run the real LifeCircle API inside the browser (Pyodide) for the live demo.

GitHub Pages can only host static files, so the live site downloads Python
(Pyodide, compiled to WebAssembly) and runs this same FastAPI app in the
visitor's browser. Requests from the page are handed straight to the ASGI app;
nothing leaves the browser and every visitor gets their own fresh demo data.

Browsers have no threads, so FastAPI's "run sync code in a thread pool" helpers
are replaced with direct calls before the app is imported.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

os.environ.setdefault("LIFECIRCLE_DB", "sqlite:////tmp/lifecircle.db")


async def _run_direct(func, *args, **kwargs):
    return func(*args, **kwargs)


@asynccontextmanager
async def _cm_direct(cm):
    with cm as value:
        yield value


def _patch_threadpool() -> None:
    import fastapi.concurrency
    import fastapi.dependencies.utils
    import fastapi.routing
    import starlette.concurrency

    for mod in (starlette.concurrency, fastapi.concurrency, fastapi.routing, fastapi.dependencies.utils):
        if hasattr(mod, "run_in_threadpool"):
            mod.run_in_threadpool = _run_direct
        if hasattr(mod, "contextmanager_in_threadpool"):
            mod.contextmanager_in_threadpool = _cm_direct


_patch_threadpool()

from app.main import app  # noqa: E402
from app.seed import reset_and_seed  # noqa: E402

reset_and_seed()


async def call(method: str, path: str, auth: str = "", body: str = "") -> list:
    """Send one HTTP-style request to the ASGI app and return [status, body]."""
    path, _, query = path.partition("?")
    headers = [(b"content-type", b"application/json")]
    if auth:
        headers.append((b"authorization", auth.encode()))
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": method.upper(), "scheme": "http", "path": path, "raw_path": path.encode(),
        "query_string": query.encode(), "root_path": "", "headers": headers,
        "client": ("browser", 0), "server": ("lifecircle", 80),
    }
    payload = (body or "").encode()
    sent = False

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": payload, "more_body": False}
        return {"type": "http.disconnect"}

    status, chunks = 500, []

    async def send(message):
        nonlocal status
        if message["type"] == "http.response.start":
            status = message["status"]
        elif message["type"] == "http.response.body":
            chunks.append(message.get("body", b""))

    await app(scope, receive, send)
    return [status, b"".join(chunks).decode()]
