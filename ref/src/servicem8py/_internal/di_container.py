#!/usr/bin/env python3
from __future__ import annotations

from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import Any, Final, TypeVar

import structlog

from di.core import Container, Token
from servicem8py.ports import Clock, HttpClient, Logger, RequestExecutor, SystemClock, TokenStore


HTTP_CLIENT_FACTORY: Final[Token[Callable[[], HttpClient]]] = Token("http_client_factory")
CLOCK: Final[Token[Clock]] = Token("clock")
LOGGER: Final[Token[Logger]] = Token("logger")
TOKEN_STORE: Final[Token[TokenStore]] = Token("token_store")

ResourceFactoryBuilder = Callable[[RequestExecutor, str], Any]
MessagingBuilder = Callable[[RequestExecutor], Any]

RESOURCE_FACTORY_BUILDER: Final[Token[ResourceFactoryBuilder]] = Token("resource_factory_builder")
MESSAGING_BUILDER: Final[Token[MessagingBuilder]] = Token("messaging_builder")


container = Container()


def _default_clock() -> Clock:
    return SystemClock()


def _default_logger() -> Logger:
    return structlog.get_logger("servicem8py")


def _default_token_store() -> TokenStore:
    from pathlib import Path

    from .token_store import FileTokenStore

    return FileTokenStore(path=Path.home() / ".servicem8" / "tokens.json")


def _default_http_client_factory() -> Callable[[], HttpClient]:
    from .http_client import HttpxClientAdapter

    def factory() -> HttpClient:
        # Always create a fresh client bound to the current running loop
        return HttpxClientAdapter()

    return factory


def _default_resource_factory_builder() -> ResourceFactoryBuilder:
    from ..resource_factory import ResourceFactory

    def factory(executor: RequestExecutor, base_url: str) -> ResourceFactory:
        return ResourceFactory(executor, base_url)

    return factory


def _default_messaging_builder() -> MessagingBuilder:
    from ..messaging import MessagingService

    def factory(executor: RequestExecutor) -> MessagingService:
        return MessagingService(executor)

    return factory


container.register(HTTP_CLIENT_FACTORY, _default_http_client_factory)
container.register(CLOCK, _default_clock)
container.register(LOGGER, _default_logger)
container.register(TOKEN_STORE, _default_token_store)
container.register(RESOURCE_FACTORY_BUILDER, _default_resource_factory_builder)
container.register(MESSAGING_BUILDER, _default_messaging_builder)


@asynccontextmanager
async def container_lifespan():
    try:
        yield container
    finally:
        await container.aclose()
from di.core import depends, inject, scoped
