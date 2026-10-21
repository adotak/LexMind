"""HTTP API and web app."""
from __future__ import annotations

import os
import time
from collections import defaultdict, deque
from importlib import resources
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__, brain, debate
from .library import Library, Section, default_library

CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; "
       "frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
SECURITY_HEADERS = {
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)


class DebateRequest(BaseModel):
    position: str = Field(min_length=10, max_length=1500)
    opponent: str = Field("", max_length=1500)


class RateLimiter:
    """Per-client sliding window. In-memory, so each server instance counts on its own."""

    def __init__(self, per_minute: int):
        self.per_minute = per_minute
        self.hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        if self.per_minute <= 0:
            return True
        now = time.monotonic()
        q = self.hits[key]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= self.per_minute:
            return False
        q.append(now)
        return True


def client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    return forwarded.split(",")[0].strip() or (request.client.host if request.client else "unknown")


def create_app(library: Library | None = None, llm: Any = None, ask_per_minute: int | None = None) -> FastAPI:
    lib = library or default_library()
    if ask_per_minute is None:
        ask_per_minute = int(os.environ.get("LEXMIND_ASK_PER_MINUTE", "10"))
    limiter = RateLimiter(ask_per_minute)
    static = resources.files("lexmind").joinpath("static")
    app = FastAPI(title="LexMind", version=__version__, docs_url="/docs", redoc_url=None)

    @app.middleware("http")
    async def security_headers(request: Request, call_next: Any) -> Response:
        response: Response = await call_next(request)
        for k, v in SECURITY_HEADERS.items():
            response.headers.setdefault(k, v)
        return response

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "version": __version__, "law": lib.law, "articles": len(lib.sections),
                "ai": llm is not None or brain.enabled()}

    @app.get("/api/library")
    def library_info() -> dict[str, Any]:
        return {"law": lib.law, "jurisdiction": lib.jurisdiction, "source_name": lib.source_name,
                "source_url": lib.source_url, "outline": lib.outline()}

    @app.get("/api/articles/{article}")
    def article(article: str) -> Section:
        section = lib.get(article)
        if section is None:
            raise HTTPException(404, f"Article {article} not found")
        return section

    @app.get("/api/search")
    def search(q: str = Query(min_length=2, max_length=300), limit: int = Query(8, ge=1, le=20)) -> list[brain.Source]:
        return [brain.Source(article=s.article, title=s.title, chapter=s.chapter, part=s.part,
                             snippet=brain.snippet(s.text), score=score) for s, score in lib.search(q, limit)]

    @app.post("/api/ask")
    def ask(body: AskRequest, request: Request) -> Any:
        if not limiter.allow(client_key(request)):
            return JSONResponse({"detail": "Too many questions. Wait a minute and try again."}, status_code=429)
        try:
            return brain.ask(lib, body.question.strip(), llm=llm)
        except Exception as exc:  # the AI provider failing shouldn't look like a LexMind bug
            raise HTTPException(502, "The AI service didn't respond. Try again in a moment.") from exc

    @app.post("/api/debate")
    def run_debate(body: DebateRequest, request: Request) -> Any:
        if not limiter.allow(client_key(request)):
            return JSONResponse({"detail": "Too many requests. Wait a minute and try again."}, status_code=429)
        try:
            return debate.debate(lib, body.position.strip(), body.opponent.strip(), llm=llm)
        except Exception as exc:
            raise HTTPException(502, "The AI service didn't respond properly. Try again in a moment.") from exc

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(str(static.joinpath("index.html")))

    app.mount("/static", StaticFiles(directory=str(static)), name="static")
    return app
