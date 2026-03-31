"""Tests for GET /api/rules (with ETag caching) and GET /health."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from app.routers import rules
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


@asynccontextmanager
async def _test_lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield


def _make_test_app() -> FastAPI:
    app = FastAPI(lifespan=_test_lifespan)
    app.include_router(rules.router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


_app = _make_test_app()


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=_app), base_url="http://test")


async def test_get_rules() -> None:
    async with _client() as c:
        resp = await c.get("/api/rules")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_get_rules_has_etag() -> None:
    async with _client() as c:
        resp = await c.get("/api/rules")
    assert "etag" in resp.headers


async def test_get_rules_count() -> None:
    async with _client() as c:
        resp = await c.get("/api/rules")
    assert len(resp.json()) == 50


async def test_get_rules_structure() -> None:
    async with _client() as c:
        resp = await c.get("/api/rules")
    for rule in resp.json():
        assert "rule_id" in rule
        assert "tags_required_a" in rule
        assert "effects" in rule


async def test_get_rules_etag_304() -> None:
    async with _client() as c:
        resp = await c.get("/api/rules")
        etag = resp.headers["etag"]
        resp2 = await c.get("/api/rules", headers={"if-none-match": etag})
    assert resp2.status_code == 304
    assert resp2.content == b""


async def test_get_rules_etag_mismatch() -> None:
    async with _client() as c:
        resp = await c.get("/api/rules", headers={"if-none-match": '"wrong"'})
    assert resp.status_code == 200


async def test_health() -> None:
    async with _client() as c:
        resp = await c.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
