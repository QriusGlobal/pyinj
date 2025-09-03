"""Performance and O(1) lookup verification tests."""

import time
from typing import Any

import pytest

from pyinj import Container, Scope, Token


class TestPerformance:
    """Test performance characteristics and O(1) lookups."""

    def test_o1_type_resolution_scaling(self):
        """Test that type resolution maintains O(1) performance as container grows."""
        container = Container()

        # Register many services to test scaling
        num_services = 1000
        services: list[tuple[Token[Any], type]] = []

        for i in range(num_services):
            class_name = f"Service{i}"
            service_class = type(class_name, (), {"value": i})
            token = Token(f"service_{i}", service_class)
            container.register(token, service_class)
            services.append((token, service_class))

        # Measure resolution time for first, middle, and last services
        test_indices = [0, num_services // 2, num_services - 1]
        resolution_times: list[float] = []

        for idx in test_indices:
            token, service_class = services[idx]

            # Warm up (exercise type path)
            container.get(service_class)

            # Time the resolution
            start_time = time.perf_counter()
            for _ in range(100):  # Multiple iterations for better measurement
                container.get(service_class)
            end_time = time.perf_counter()

            avg_time = (end_time - start_time) / 100
            resolution_times.append(avg_time)

        # O(1) means resolution time should be roughly constant
        # Allow some variance but not more than 2x difference
        min_time = min(resolution_times)
        max_time = max(resolution_times)

        assert max_time <= min_time * 2, (
            f"Resolution times vary too much: {resolution_times}"
        )

        # Also check absolute performance - should be very fast
        for resolve_time in resolution_times:
            assert resolve_time < 0.001, f"Resolution too slow: {resolve_time:.6f}s"

    def test_basic_resolution_performance(self):
        """Simplified resolution performance without protocol indirection."""
        container = Container()
        num = 200
        tokens: list[tuple[Token[Any], type]] = []
        for i in range(num):
            cls = type(f"Impl{i}", (), {"id": i})
            tok = Token(f"impl_{i}", cls)
            container.register(tok, cls)
            tokens.append((tok, cls))

        # Warmup
        for tok, _ in tokens[:5]:
            container.get(tok)

        # Measure
        start = time.perf_counter()
        for _ in range(100):
            for tok, _cls in tokens:
                container.get(tok)
        dt = time.perf_counter() - start
        per_call = dt / (100 * num)
        assert per_call < 0.0005, f"Resolution too slow: {per_call:.6f}s"

    def test_injection_cache_performance(self):
        """Test that injection caching improves performance."""
        container = Container()

        class Service1:
            def __init__(self):
                self.value = "service1"

        class Service2:
            def __init__(self):
                self.value = "service2"

        class Service3:
            def __init__(self):
                self.value = "service3"

        token1 = Token("service1", Service1)
        token2 = Token("service2", Service2)
        token3 = Token("service3", Service3)

        container.register(token1, Service1)
        container.register(token2, Service2)
        container.register(token3, Service3)

        @container.inject
        def complex_function(s1: Service1, s2: Service2, s3: Service3) -> str:
            return f"{s1.value}-{s2.value}-{s3.value}"

        # First call should cache injection metadata
        first_call_start = time.perf_counter()
        result1 = complex_function()
        first_call_end = time.perf_counter()

        first_call_time = first_call_end - first_call_start

        # Subsequent calls should be faster due to caching
        cached_call_times: list[float] = []
        for _ in range(10):
            start = time.perf_counter()
            result = complex_function()
            end = time.perf_counter()
            cached_call_times.append(end - start)
            assert result == result1  # Verify correctness

        avg_cached_time = sum(cached_call_times) / len(cached_call_times)

        # Cached calls should be significantly faster than first call
        # (First call includes inspection overhead)
        assert avg_cached_time <= first_call_time, (
            f"Cached calls not faster: first={first_call_time:.6f}, "
            f"avg_cached={avg_cached_time:.6f}"
        )

    def test_singleton_access_performance(self):
        """Test that singleton access is fast after first creation."""
        container = Container()

        class ExpensiveService:
            def __init__(self):
                # Simulate expensive initialization
                time.sleep(0.01)
                self.value = "expensive"

        token = Token("expensive", ExpensiveService)
        container.register(token, ExpensiveService, Scope.SINGLETON)

        # First access includes creation time
        first_access_start = time.perf_counter()
        service1 = container.get(token)
        first_access_end = time.perf_counter()

        first_access_time = first_access_end - first_access_start
        assert first_access_time >= 0.01  # Should include creation time

        # Subsequent accesses should be very fast
        subsequent_times: list[float] = []
        for _ in range(100):
            start = time.perf_counter()
            service = container.get(token)
            end = time.perf_counter()
            subsequent_times.append(end - start)
            assert service is service1  # Same instance

        avg_subsequent_time = sum(subsequent_times) / len(subsequent_times)

        # Subsequent accesses should be orders of magnitude faster
        assert avg_subsequent_time < 0.001, (
            f"Singleton access too slow: {avg_subsequent_time:.6f}s"
        )
        assert avg_subsequent_time < first_access_time / 10, (
            f"Singleton access not fast enough: "
            f"first={first_access_time:.6f}, avg_subsequent={avg_subsequent_time:.6f}"
        )

    def test_large_container_registration_performance(self):
        """Test registration performance with large numbers of services."""
        container = Container()

        # Register many services and measure time
        num_services = 1000
        registration_times: list[float] = []

        for i in range(num_services):
            service_class = type(f"Service{i}", (), {"id": i})
            token = Token(f"service_{i}", service_class)

            start_time = time.perf_counter()
            container.register(token, service_class)
            end_time = time.perf_counter()

            registration_times.append(end_time - start_time)

        # Registration time should remain relatively constant (not grow linearly)
        early_times = registration_times[:100]
        late_times = registration_times[-100:]

        avg_early = sum(early_times) / len(early_times)
        avg_late = sum(late_times) / len(late_times)

        # Late registrations shouldn't be significantly slower than early ones
        assert avg_late <= avg_early * 2, (
            f"Registration performance degrades: early={avg_early:.6f}, late={avg_late:.6f}"
        )

    def test_memory_efficiency(self):
        """Test that container doesn't use excessive memory."""
        import sys

        container = Container()

        # Measure initial memory usage using public views
        initial_size = sys.getsizeof(container) + sum(
            sys.getsizeof(obj)
            for obj in [
                container.get_providers_view(),
                container.resources_view(),
            ]
        )

        # Register many services
        num_services = 100
        for i in range(num_services):
            service_class = type(f"Service{i}", (), {"id": i})
            token = Token(f"service_{i}", service_class)
            container.register(token, service_class, Scope.SINGLETON)
            # Create some singletons
            if i % 10 == 0:
                container.get(token)

        # Measure final memory usage
        final_size = sys.getsizeof(container) + sum(
            sys.getsizeof(obj)
            for obj in [
                container.get_providers_view(),
                container.resources_view(),
            ]
        )

        # Memory growth should be reasonable (not exponential)
        memory_growth = final_size - initial_size
        memory_per_service = memory_growth / num_services

        # Should be less than 1KB per service on average
        assert memory_per_service < 1024, (
            f"Memory usage too high: {memory_per_service:.1f} bytes per service"
        )

    @pytest.mark.slow
    def test_stress_performance(self):
        """Stress test with many concurrent operations."""
        from concurrent.futures import ThreadPoolExecutor

        container = Container()

        # Pre-register services
        num_services = 50
        tokens: list[Token[Any]] = []

        for i in range(num_services):
            service_class = type(f"Service{i}", (), {"id": i, "call_count": 0})
            token = Token(f"service_{i}", service_class)
            container.register(token, service_class, Scope.SINGLETON)
            tokens.append(token)

        def stress_worker(worker_id: int):
            """Perform many operations rapidly."""
            operations = 1000
            start_time = time.perf_counter()

            for i in range(operations):
                # Mix of different operations
                token_idx = i % len(tokens)
                token = tokens[token_idx]

                service = container.get(token)
                service.call_count += 1

                # Occasional override operations
                if i % 50 == 0:
                    container.override(token, service)

            end_time = time.perf_counter()
            return end_time - start_time

        # Run stress test with multiple workers
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures: list[Any] = [executor.submit(stress_worker, i) for i in range(20)]
            completion_times: list[float] = [future.result() for future in futures]

        avg_completion_time = sum(completion_times) / len(completion_times)

        # Should complete 1000 operations per worker in reasonable time
        assert avg_completion_time < 1.0, (
            f"Stress test too slow: {avg_completion_time:.3f}s per 1000 operations"
        )
