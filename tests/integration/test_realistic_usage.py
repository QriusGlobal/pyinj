"""Realistic integration tests emulating user projects with async libs.

These tests demonstrate typical project usage of pyinj with httpx and
SQLAlchemy async. Playwright-style usage is simulated via a fake to avoid
browser downloads while exercising DI patterns and cleanup behavior.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
import httpx
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.sql import text

from pyinj.container import Container
from pyinj.tokens import Scope, Token
from pyinj.injection import Inject, inject


def _make_mock_httpx() -> httpx.AsyncClient:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"path": request.url.path})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://svc")


@pytest.mark.asyncio
async def test_user_style_project_di_with_httpx_and_sqlalchemy() -> None:
    container = Container()

    # Tokens a user would define centrally
    httpx_token = Token("http_client", httpx.AsyncClient, scope=Scope.SINGLETON)
    engine_token = Token("db_engine", AsyncEngine, scope=Scope.SINGLETON)
    session_token = Token("db_session", AsyncSession, scope=Scope.REQUEST)

    # Providers users would register during app startup
    async def create_http_client() -> httpx.AsyncClient:
        await asyncio.sleep(0)
        return _make_mock_httpx()

    async def create_engine() -> AsyncEngine:
        eng = create_async_engine("sqlite+aiosqlite:///:memory:")
        # warmup connect
        async with eng.begin() as conn:  # pragma: no cover - trivial
            await conn.execute(text("select 1"))
        return eng

    async def create_session() -> AsyncSession:
        engine = await container.aget(engine_token)
        Session = async_sessionmaker(engine, expire_on_commit=False)
        return Session()

    container.register(httpx_token, create_http_client)
    container.register(engine_token, create_engine)
    container.register(session_token, create_session)

    # User endpoint using @inject
    @inject(container=container)
    async def endpoint(
        user_id: int,
        client: Inject[httpx.AsyncClient],
        db: Inject[AsyncSession],
    ) -> dict[str, Any]:
        r = await client.get(f"/users/{user_id}")
        rows = (await db.execute(text("select 42 as answer"))).all()
        return {"status": r.status_code, "path": r.json()["path"], "rows": [dict(row._mapping) for row in rows]}

    # Simulate concurrent requests with isolated scopes
    async def call(uid: int) -> dict[str, Any]:
        async with container.async_request_scope():
            return await endpoint(uid)

    results = await asyncio.gather(*(call(i) for i in range(10)))
    assert all(r["status"] == 200 for r in results)
    assert all(r["path"].startswith("/users/") for r in results)
    assert all(r["rows"][0]["answer"] == 42 for r in results)

    # Singleton instances created only once
    c1 = await container.aget(httpx_token)
    c2 = await container.aget(httpx_token)
    assert c1 is c2

    eng1 = await container.aget(engine_token)
    eng2 = await container.aget(engine_token)
    assert eng1 is eng2

    # Sessions are request-scoped; outside scope not cached
    assert container.resolve_from_context(session_token) is None

    await container.aclose()


@pytest.mark.asyncio
async def test_playwright_style_fake_browser_with_cleanup() -> None:
    container = Container()

    class FakeBrowser:
        def __init__(self) -> None:
            self.closed = False

        async def aclose(self) -> None:
            self.closed = True

        async def goto(self, url: str) -> dict[str, str]:  # pragma: no cover - trivial
            await asyncio.sleep(0)
            return {"url": url}

    browser_token = Token("browser", FakeBrowser, scope=Scope.SINGLETON)

    async def create_browser() -> FakeBrowser:
        await asyncio.sleep(0)
        return FakeBrowser()

    container.register(browser_token, create_browser)

    # Emulate concurrent test runners using the container
    async def worker(i: int) -> bool:
        b = await container.aget(browser_token)
        await b.goto(f"https://example/{i}")
        return True

    ok = await asyncio.gather(*(worker(i) for i in range(20)))
    assert all(ok)

    b = await container.aget(browser_token)
    await container.aclose()
    assert b.closed is True
