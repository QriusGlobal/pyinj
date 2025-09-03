"""Realistic integration tests emulating user projects with async libs.

These tests demonstrate typical project usage of pyinj with httpx and
an async DB client (aiosqlite). Playwright-style usage is simulated via a fake to avoid
browser downloads while exercising DI patterns and cleanup behavior.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
import httpx
import aiosqlite

from pyinj.container import Container
from pyinj.tokens import Scope, Token
from pyinj.injection import Inject, inject
from typing import Annotated


def _make_mock_httpx() -> httpx.AsyncClient:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"path": request.url.path})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://svc")


@pytest.mark.asyncio
async def test_user_style_project_di_with_httpx_and_aiosqlite() -> None:
    container = Container()

    # Tokens a user would define centrally
    httpx_token = Token("http_client", httpx.AsyncClient, scope=Scope.SINGLETON)
    db_token = Token("db", aiosqlite.Connection, scope=Scope.REQUEST)

    # Providers users would register during app startup
    async def create_http_client() -> httpx.AsyncClient:
        await asyncio.sleep(0)
        return _make_mock_httpx()

    async def create_db() -> aiosqlite.Connection:
        db = await aiosqlite.connect(":memory:")
        await db.execute("create table t(x int)")
        await db.execute("insert into t(x) values (42)")
        await db.commit()
        return db

    container.register(httpx_token, create_http_client)
    container.register(db_token, create_db)

    # User endpoint using @inject
    @inject(container=container)
    async def endpoint(
        user_id: int,
        client: Annotated[httpx.AsyncClient, Inject()],
        db: Annotated[aiosqlite.Connection, Inject()],
    ) -> dict[str, Any]:
        r = await client.get(f"/users/{user_id}")
        cur = await db.execute("select x from t")
        rows = await cur.fetchall()
        return {"status": r.status_code, "path": r.json()["path"], "rows": [{"answer": row[0]} for row in rows]}

    # Simulate concurrent requests with isolated scopes
    from typing import Awaitable, Callable, cast
    async def call(uid: int) -> dict[str, Any]:
        async with container.async_request_scope():
            wrapped = cast(Callable[[int], Awaitable[dict[str, Any]]], endpoint)
            return await wrapped(uid)

    results = await asyncio.gather(*(call(i) for i in range(10)))
    assert all(r["status"] == 200 for r in results)
    assert all(r["path"].startswith("/users/") for r in results)
    assert all(r["rows"][0]["answer"] == 42 for r in results)

    # Singleton instances created only once
    c1 = await container.aget(httpx_token)
    c2 = await container.aget(httpx_token)
    assert c1 is c2

    # DB is request-scoped; outside scope not cached
    assert container.resolve_from_context(db_token) is None

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
