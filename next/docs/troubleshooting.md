# Troubleshooting - PyInj

[ ](https://github.com/QriusGlobal/pyinj/edit/master/docs/troubleshooting.md "Edit this page")

# Troubleshooting Guide¶

This guide covers common issues, error messages, and solutions when using PyInj.

## Common Issues¶

### 1\. Circular Dependencies¶

**Problem:** Services depend on each other, creating a circular dependency.

**Error Message:**
    
    
    pyinj.exceptions.CircularDependencyError: Cannot resolve token 'service_a':
      Resolution chain: service_a -> service_b -> service_a
      Cause: Circular dependency detected: service_a -> service_b -> service_a
    

**Example:**
    
    
    class ServiceA:
        def __init__(self, service_b: ServiceB):
            self.service_b = service_b
    
    class ServiceB:  
        def __init__(self, service_a: ServiceA):
            self.service_a = service_a
    
    # This creates a circular dependency
    container.register(SERVICE_A, lambda: ServiceA(container.get(SERVICE_B)))
    container.register(SERVICE_B, lambda: ServiceB(container.get(SERVICE_A)))
    

**Solutions:**

#### Solution 1: Redesign Architecture¶
    
    
    # Extract common functionality
    class SharedService:
        def common_functionality(self) -> str:
            return "shared logic"
    
    class ServiceA:
        def __init__(self, shared: SharedService):
            self.shared = shared
    
    class ServiceB:
        def __init__(self, shared: SharedService):
            self.shared = shared
    
    # No circular dependency
    container.register(SHARED_SERVICE, SharedService, scope=Scope.SINGLETON)
    container.register(SERVICE_A, lambda: ServiceA(container.get(SHARED_SERVICE)))
    container.register(SERVICE_B, lambda: ServiceB(container.get(SHARED_SERVICE)))
    

#### Solution 2: Lazy Injection¶
    
    
    from typing import Callable
    
    class ServiceA:
        def __init__(self, get_service_b: Callable[[], ServiceB]):
            self._get_service_b = get_service_b
            self._service_b: ServiceB | None = None
    
        @property
        def service_b(self) -> ServiceB:
            if self._service_b is None:
                self._service_b = self._get_service_b()
            return self._service_b
    
    # Use lazy injection
    container.register(SERVICE_A, lambda: ServiceA(lambda: container.get(SERVICE_B)))
    container.register(SERVICE_B, ServiceBImplementation)
    

### 2\. Type Checker Issues¶

**Problem:** Static type checkers report errors with PyInj code.

#### Issue: "Cannot assign to Token[X]"¶

**Error:**
    
    
    error: Argument 2 to "register" has incompatible type "int"; expected "Callable[[], str]"
    

**Cause:**
    
    
    TOKEN = Token[str]("my_token")
    container.register(TOKEN, 123)  # Type error: int not assignable to str
    

**Solution:**
    
    
    # Fix the type or provider
    TOKEN = Token[int]("my_token")
    container.register(TOKEN, 123)  # OK
    
    # Or fix the provider
    TOKEN = Token[str]("my_token")
    container.register(TOKEN, lambda: "123")  # OK
    

#### Issue: "Protocol not satisfied"¶

**Error:**
    
    
    error: Argument 2 to "register" has incompatible type "IncompleteService"; 
    expected "Callable[[], Logger]"
    

**Cause:**
    
    
    from typing import Protocol
    
    class Logger(Protocol):
        def info(self, message: str) -> None: ...
        def error(self, message: str) -> None: ...
    
    class IncompleteLogger:
        def info(self, message: str) -> None:
            print(message)
        # Missing error method!
    
    LOGGER = Token[Logger]("logger")
    container.register(LOGGER, IncompleteLogger)  # Type error
    

**Solution:**
    
    
    class CompleteLogger:
        def info(self, message: str) -> None:
            print(f"INFO: {message}")
    
        def error(self, message: str) -> None:
            print(f"ERROR: {message}")
    
    container.register(LOGGER, CompleteLogger)  # OK
    

### 3\. Async/Sync Mixing Issues¶

**Problem:** Mixing async and sync contexts incorrectly.

#### Issue: Async Provider in Sync Context¶

**Error:**
    
    
    RuntimeError: Cannot resolve async provider in sync context
    

**Cause:**
    
    
    async def create_async_service() -> AsyncService:
        service = AsyncService()
        await service.initialize()
        return service
    
    container.register(ASYNC_SERVICE, create_async_service)
    
    # This fails - async provider in sync context
    service = container.get(ASYNC_SERVICE)  # Error!
    

**Solution:**
    
    
    # Use async resolution
    service = await container.aget(ASYNC_SERVICE)  # OK
    

#### Issue: AsyncCleanupRequiredError¶

**Error:**
    
    
    pyinj.exceptions.AsyncCleanupRequiredError: Resource AsyncDatabaseClient requires 
    asynchronous cleanup. Use an async request/session scope.
    

**Cause:**
    
    
    # Register async-only resource
    container.register_context_async(ASYNC_DB, async_database_context)
    
    # Try to use sync cleanup
    with container:  # Error! Async resource needs async cleanup
        db = await container.aget(ASYNC_DB)
    

**Solution:**
    
    
    # Use async cleanup
    async def main():
        db = await container.aget(ASYNC_DB)
        # Use database
        await container.aclose()  # Proper async cleanup
    
    asyncio.run(main())
    

### 4\. Resolution Errors¶

**Problem:** PyInj cannot resolve a requested dependency.

#### Issue: Missing Provider¶

**Error:**
    
    
    pyinj.exceptions.ResolutionError: Cannot resolve token 'database':
      Resolution chain: user_service -> database
      Cause: No provider registered for token 'database'
    

**Cause:**
    
    
    USER_SERVICE = Token[UserService]("user_service")
    DATABASE = Token[Database]("database")
    
    # Register user service but forget database
    container.register(USER_SERVICE, lambda: UserService(container.get(DATABASE)))
    # DATABASE never registered!
    
    user_service = container.get(USER_SERVICE)  # Error!
    

**Solution:**
    
    
    # Register all required dependencies
    container.register(DATABASE, PostgreSQLDatabase)
    container.register(USER_SERVICE, lambda: UserService(container.get(DATABASE)))
    

#### Issue: Type Not Found for Plain Annotation¶

**Error:**
    
    
    pyinj.exceptions.ResolutionError: Cannot resolve token for type 'Database':
      Resolution chain: root
      Cause: No provider registered for type 'Database'
    

**Cause:**
    
    
    @inject
    def service(db: Database) -> None:  # Plain type annotation
        pass
    
    # But no registration for Database type
    service()  # Error!
    

**Solution:**

**Option 1: Register by Type**
    
    
    container.register(Database, PostgreSQLDatabase)
    
    @inject(container=container)
    def service(db: Database) -> None:
        pass
    

**Option 2: Use Explicit Tokens**
    
    
    DATABASE = Token[Database]("database")
    container.register(DATABASE, PostgreSQLDatabase)
    
    @inject
    def service(db: Annotated[Database, Inject(lambda: container.get(DATABASE))]) -> None:
        pass
    

### 5\. Scope-Related Issues¶

#### Issue: Request Scope Outside Context¶

**Error:**
    
    
    RuntimeError: No active request scope for registering cleanup
    

**Cause:**
    
    
    # Try to register request-scoped cleanup outside request scope
    container.register_context_sync(REQUEST_TOKEN, some_context)
    container._register_request_cleanup_sync(cleanup_fn)  # Error!
    

**Solution:**
    
    
    # Use request scope properly
    with container.request_scope():
        # Request-scoped operations here
        service = container.get(REQUEST_SCOPED_TOKEN)
    

#### Issue: Scope Mismatch¶

**Problem:** Dependencies have incompatible scopes.
    
    
    # Singleton depends on request-scoped service
    SINGLETON_SERVICE = Token[Service]("singleton", scope=Scope.SINGLETON)
    REQUEST_SERVICE = Token[RequestService]("request", scope=Scope.REQUEST)
    
    container.register(REQUEST_SERVICE, RequestServiceImpl)
    container.register(
        SINGLETON_SERVICE,
        lambda: Service(container.get(REQUEST_SERVICE))  # Problem!
    )
    

**Issue:** Singleton will get the first request-scoped instance and keep it forever.

**Solution:**
    
    
    # Redesign: singleton should not depend on request-scoped
    # Or make both request-scoped
    SINGLETON_SERVICE = Token[Service]("service", scope=Scope.REQUEST)
    

### 6\. Import and Module Issues¶

#### Issue: Circular Imports¶

**Error:**
    
    
    ImportError: cannot import name 'UserService' from partially initialized module
    

**Cause:**
    
    
    # services/user.py
    from services.email import EmailService
    
    class UserService:
        def __init__(self, email: EmailService): ...
    
    # services/email.py
    from services.user import UserService  # Circular import!
    
    class EmailService:
        def __init__(self, user: UserService): ...
    

**Solutions:**

**Option 1: Protocol Imports**
    
    
    # protocols.py
    from typing import Protocol
    
    class UserServiceProtocol(Protocol):
        def create_user(self, data: dict) -> dict: ...
    
    class EmailServiceProtocol(Protocol):
        def send_email(self, to: str, subject: str) -> bool: ...
    
    # services/user.py
    from protocols import EmailServiceProtocol
    
    class UserService:
        def __init__(self, email: EmailServiceProtocol): ...
    
    # services/email.py  
    from protocols import UserServiceProtocol
    
    class EmailService:
        def __init__(self, user: UserServiceProtocol): ...
    

**Option 2: Type Imports Only**
    
    
    # services/user.py
    from typing import TYPE_CHECKING
    
    if TYPE_CHECKING:
        from services.email import EmailService
    
    class UserService:
        def __init__(self, email: "EmailService"): ...
    

### 7\. Performance Issues¶

#### Issue: Slow Container Resolution¶

**Problem:** Container resolution is slower than expected.

**Debugging:**
    
    
    import time
    from pyinj import Container, Token
    
    container = Container()
    
    # Time resolution
    start = time.time()
    for _ in range(1000):
        service = container.get(SERVICE_TOKEN)
    end = time.time()
    
    print(f"Average resolution time: {(end - start) / 1000 * 1000:.2f}ms")
    

**Common Causes:**

  1. **Heavy provider functions**
         
         # Slow provider
         def create_heavy_service() -> Service:
             time.sleep(0.1)  # Simulated heavy work
             return Service()
         
         container.register(SERVICE_TOKEN, create_heavy_service, scope=Scope.TRANSIENT)
         

**Solution:** Use appropriate scope 
    
    
    # Cache expensive creation with singleton scope
    container.register(SERVICE_TOKEN, create_heavy_service, scope=Scope.SINGLETON)
    

  1. **Complex dependency chains**
         
         # Many nested dependencies
         container.register(A, lambda: A(container.get(B)))
         container.register(B, lambda: B(container.get(C)))
         container.register(C, lambda: C(container.get(D)))
         # ... many more levels
         

**Solution:** Flatten dependency hierarchy or use caching.

### 8\. Testing Issues¶

#### Issue: Test Pollution¶

**Problem:** Tests affect each other due to shared container state.
    
    
    class TestService:
        container = Container()  # Shared between tests - BAD!
    
        def test_user_creation(self):
            self.container.override(DB_TOKEN, mock_db)
            # Test logic
    
        def test_user_deletion(self):
            # This test affected by previous override!
            service = self.container.get(USER_SERVICE_TOKEN)
    

**Solution:**
    
    
    class TestService:
        def setup_method(self):
            self.container = Container()  # Fresh container per test
    
        def teardown_method(self):
            self.container.clear_overrides()
    

#### Issue: Mock Assertion Failures¶

**Problem:** Mock assertions fail unexpectedly.
    
    
    def test_user_service(self):
        mock_db = Mock(spec=Database)
        container.override(DB_TOKEN, mock_db)
    
        service = container.get(USER_SERVICE_TOKEN)
        service.create_user("test@example.com", "Test")
    
        # This might fail if the service makes multiple calls
        mock_db.create_user.assert_called_once()
    

**Debug with:**
    
    
    # See all calls made to mock
    print(mock_db.method_calls)
    print(mock_db.create_user.call_count)
    print(mock_db.create_user.call_args_list)
    

## Debugging Techniques¶

### 1\. Enable Debug Logging¶
    
    
    import logging
    
    # Enable PyInj debug logging
    logging.basicConfig(level=logging.DEBUG)
    logger = logging.getLogger("pyinj")
    
    container = Container()
    # Resolution steps will be logged
    

### 2\. Inspect Container State¶
    
    
    # Check registered providers
    print("Registered tokens:", list(container._providers.keys()))
    
    # Check singleton cache
    print("Singletons:", list(container._singletons.keys()))
    
    # Check overrides
    print("Overrides:", list(container._overrides.keys()) if hasattr(container, '_overrides') else [])
    

### 3\. Resolution Chain Analysis¶
    
    
    from pyinj.exceptions import ResolutionError
    
    try:
        service = container.get(PROBLEMATIC_TOKEN)
    except ResolutionError as e:
        print(f"Failed token: {e.token.name}")
        print(f"Resolution chain: {[t.name for t in e.chain]}")
        print(f"Root cause: {e.cause}")
    

### 4\. Provider Function Inspection¶
    
    
    import inspect
    
    # Check provider function signature
    provider = container._providers[TOKEN]
    if callable(provider):
        sig = inspect.signature(provider)
        print(f"Provider signature: {sig}")
        print(f"Provider source: {inspect.getsource(provider)}")
    

### 5\. Type Checking Verification¶
    
    
    # Verify protocol compliance at runtime
    from typing import runtime_checkable
    
    @runtime_checkable
    class Logger(Protocol):
        def info(self, message: str) -> None: ...
    
    logger_instance = container.get(LOGGER_TOKEN)
    assert isinstance(logger_instance, Logger), f"Logger instance {logger_instance} does not satisfy Logger protocol"
    

## Getting Help¶

### 1\. Error Context¶

When reporting issues, include:

  * Complete error message and stack trace
  * Minimal reproduction code
  * Python and PyInj versions
  * Type checker (mypy/basedpyright) version if relevant

### 2\. Code Review Checklist¶

Before asking for help, verify:

  * [ ] All dependencies are registered
  * [ ] Token types match provider return types 
  * [ ] Circular dependencies are avoided
  * [ ] Appropriate scopes are used
  * [ ] Async/sync contexts are correct
  * [ ] Test containers are isolated

### 3\. Common Solutions Summary¶

Problem | Solution  
---|---  
Circular dependencies | Redesign architecture or use lazy injection  
Type errors | Match token types with providers  
Async/sync mixing | Use `aget()` for async, `get()` for sync  
Missing providers | Register all required dependencies  
Test pollution | Use fresh containers per test  
Performance issues | Use appropriate scopes (singleton for expensive)  
Import errors | Use protocols or TYPE_CHECKING imports  
  
This should help you diagnose and fix most common PyInj issues. For complex problems, consider breaking down your dependency graph and testing components in isolation.