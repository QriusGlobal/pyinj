#!/usr/bin/env python3
"""Direct test runner for consolidated implementation."""

import sys
import os
from pathlib import Path

# Add src to path
src_path = Path(__file__).resolve().parent / "src"
sys.path.insert(0, str(src_path))

# Import our tests
if __name__ == "__main__":
    # Run basic token tests
    print("Testing Token implementation...")
    from tests.test_tokens import TestToken, TestTokenFactory, TestScope
    
    # Create test instances
    token_tests = TestToken()
    factory_tests = TestTokenFactory()
    scope_tests = TestScope()
    
    # Run token tests
    try:
        token_tests.test_token_creation()
        print("✓ Token creation")
        
        token_tests.test_token_immutability()
        print("✓ Token immutability")
        
        token_tests.test_token_hashing()
        print("✓ Token hashing")
        
        token_tests.test_token_equality()
        print("✓ Token equality")
        
        token_tests.test_token_with_qualifier()
        print("✓ Token with qualifier")
        
        token_tests.test_token_with_tags()
        print("✓ Token with tags")
        
        token_tests.test_token_with_scope()
        print("✓ Token scope modification")
        
        token_tests.test_token_qualified_name()
        print("✓ Token qualified name")
        
        
        # Factory tests
        factory_tests.test_factory_creation()
        print("✓ Factory creation")
        
        factory_tests.test_factory_caching()
        print("✓ Factory caching")
        
        factory_tests.test_factory_singleton_method()
        print("✓ Factory singleton method")
        
        factory_tests.test_factory_cache_clearing()
        print("✓ Factory cache clearing")
        
        # Scope tests
        scope_tests.test_scope_values()
        print("✓ Scope enum values")
        
        scope_tests.test_scope_comparison()
        print("✓ Scope comparison")
        
        print("\n✅ All Token tests passed!")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # Test container
    print("\nTesting Container implementation...")
    from tests.test_container import TestContainer
    
    container_tests = TestContainer()
    
    try:
        container_tests.test_container_initialization()
        print("✓ Container initialization")
        
        container_tests.test_register_provider()
        print("✓ Provider registration")
        
        container_tests.test_register_with_type()
        print("✓ Type-based registration")
        
        container_tests.test_get_simple()
        print("✓ Simple dependency resolution")
        
        container_tests.test_get_singleton()
        print("✓ Singleton resolution")
        
        container_tests.test_given_instances()
        print("✓ Given instances")
        
        container_tests.test_has_method()
        print("✓ Has method")
        
        print("\n✅ All Container tests passed!")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # Smoke-test DI_SPEC: use_overrides and aclose
    print("\nTesting DI_SPEC extras (overrides, aclose)...")
    try:
        from pyinj.container import Container
        from pyinj.tokens import Token

        c = Container()
        t = Token("name", str)
        c.register(t, lambda: "original")
        assert c.get(t) == "original"
        with c.use_overrides({t: "override"}):
            assert c.get(t) == "override"
        assert c.get(t) == "original"

        import asyncio as _asyncio
        _asyncio.get_event_loop().run_until_complete(c.aclose())
        print("✓ Overrides and aclose")
    except Exception as e:
        print(f"\n❌ DI_SPEC extras failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    print("\n🎉 All tests passed successfully!")
