"""Enhanced singular Container tests (consolidated)."""

import pytest

from pyinj.container import Container
from pyinj.tokens import Scope, Token


class Database:
    def __init__(self) -> None:
        self.id = id(self)


class Cache:
    def get(self, key: str) -> str:  # pragma: no cover - trivial
        return f"cached_{key}"


class Service:
    def __init__(self, db: Database, cache: Cache) -> None:
        self.db = db
        self.cache = cache


class TestContainer:
    def test_container_initialization(self) -> None:
        container = Container()
        assert hasattr(container, "tokens")
        assert len(container.get_providers_view()) == 0
        assert len(container.resources_view()) == 0
        assert container.resolve_given(int) is None
        stats = container.get_stats()
        assert stats["singletons"] == 0
        assert stats["cache_hits"] == 0
        assert stats["cache_misses"] == 0

    def test_register_provider(self) -> None:
        container = Container()

        def create_db() -> Database:
            return Database()

        result = container.register(Token("database", Database), create_db)
        assert result is container
        assert len(container.get_providers_view()) == 1

    def test_register_with_type(self) -> None:
        container = Container()

        def create_db() -> Database:
            return Database()

        container.register(Database, create_db)
        assert len(container.get_providers_view()) == 1
        token = list(container.get_providers_view().keys())[0]
        assert token.type_ == Database

    def test_register_with_string(self) -> None:
        container = Container()

        def create_db() -> Database:
            return Database()

        with pytest.raises(TypeError):
            container.register("my_database", create_db)  # type: ignore[arg-type]

    def test_register_validates_provider(self) -> None:
        container = Container()
        with pytest.raises(TypeError):
            container.register(Token("database", Database), "not_callable")  # type: ignore[arg-type]

    def test_register_chaining(self) -> None:
        container = (
            Container()
            .register(Token("db", Database), lambda: Database())
            .register(Token("cache", Cache), lambda: Cache())
            .register(Token("service", Service), lambda: Service(Database(), Cache()))
        )
        assert len(container.get_providers_view()) == 3

    def test_register_scoped_methods(self) -> None:
        container = Container()
        container.register_singleton(Database, lambda: Database())
        container.register_request(Cache, lambda: Cache())
        container.register_transient(Service, lambda: Service(Database(), Cache()))
        tokens = list(container.get_providers_view().keys())
        assert any(t.scope == Scope.SINGLETON for t in tokens)
        assert any(t.scope == Scope.REQUEST for t in tokens)
        assert any(t.scope == Scope.TRANSIENT for t in tokens)

    def test_register_value(self) -> None:
        container = Container()
        db_instance = Database()
        container.register_value(Database, db_instance)
        stats = container.get_stats()
        assert stats["singletons"] == 1
        assert container.get(Database) is db_instance

    def test_get_simple(self) -> None:
        container = Container()
        db_instance = Database()
        container.register(Database, lambda: db_instance)
        result = container.get(Database)
        assert result is db_instance

    def test_get_singleton(self) -> None:
        container = Container()
        call_count = 0

        def create_db() -> Database:
            nonlocal call_count
            call_count += 1
            return Database()

        container.register(Database, create_db, scope=Scope.SINGLETON)
        db1 = container.get(Database)
        db2 = container.get(Database)
        assert db1 is db2
        assert call_count == 1

    def test_given_instances(self) -> None:
        container = Container()
        container.given(int, 42)
        assert container.resolve_given(int) == 42

    def test_has_method(self) -> None:
        container = Container()
        assert container.has(Token("unknown", str)) is False
        container.given(str, "value")
        assert container.has(str) is True


class TestTypeResolution:
    """Test type-based resolution using direct types."""

    def test_resolve_by_concrete_type(self):
        container = Container()

        class ServiceX:
            def __init__(self) -> None:
                self.value = 42

        container.register(ServiceX, ServiceX)
        resolved = container.get(ServiceX)
        assert isinstance(resolved, ServiceX)
        assert resolved.value == 42
