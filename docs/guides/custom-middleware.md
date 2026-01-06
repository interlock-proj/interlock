# Custom Middleware

Build custom middleware to handle cross-cutting concerns in your application.

## Goal

Create middleware that intercepts command and query execution for logging, 
validation, authorization, caching, and more.

## Prerequisites

- Understanding of [Commands](../concepts/commands.md) and [Queries](../concepts/queries.md)
- Familiarity with the [Tutorial: Middleware](../tutorial/06-middleware.md)

## What is Middleware?

Middleware wraps command and query execution in a chain, allowing you to:

- Execute code **before** the message reaches its handler
- Execute code **after** the message has been handled
- **Short-circuit** execution (reject messages, return cached values)
- **Transform** messages before they're handled
- Handle **exceptions** from downstream handlers

The same middleware chain serves both commands (write operations) and queries 
(read operations), enabling unified cross-cutting concerns.

## Creating Custom Middleware

Middleware extends `Middleware` and uses the `@intercepts` decorator to 
mark interceptor methods:

```python
from interlock.application.middleware import Middleware, Handler
from interlock.routing import intercepts
from interlock.domain import Command, Query
from pydantic import BaseModel

class TimingMiddleware(Middleware):
    """Measure and log execution time for commands and queries."""

    @intercepts
    async def time_command(
        self, 
        command: Command,  # (1)!
        next: Handler  # (2)!
    ):
        import time
        
        start = time.perf_counter()
        try:
            return await next(command)  # (3)!
        finally:
            elapsed = time.perf_counter() - start
            print(f"Command {type(command).__name__} completed in {elapsed:.3f}s")
    
    @intercepts
    async def time_query(
        self, 
        query: Query,  # (4)!
        next: Handler
    ):
        import time
        
        start = time.perf_counter()
        try:
            return await next(query)
        finally:
            elapsed = time.perf_counter() - start
            print(f"Query {type(query).__name__} completed in {elapsed:.3f}s")
```

1. Type annotation determines which messages are intercepted
2. `next` is the next handler in the chain (middleware, aggregate, or projection)
3. Call `await next(message)` to continue the chain; return the result
4. Separate interceptor for queries—or use `BaseModel` to intercept everything

### Intercepting All Messages

To intercept both commands and queries with a single method, annotate with 
`BaseModel` (the common base of both):

```python
class UnifiedTimingMiddleware(Middleware):
    """Time all commands and queries."""

    @intercepts
    async def time_all(self, message: BaseModel, next: Handler):
        import time
        
        start = time.perf_counter()
        try:
            return await next(message)
        finally:
            elapsed = time.perf_counter() - start
            print(f"{type(message).__name__} completed in {elapsed:.3f}s")
```

## Dependency Injection

Middleware constructors support dependency injection. Dependencies are resolved 
from the DI container when the middleware is instantiated:

```python
from abc import ABC, abstractmethod

class AuditService(ABC):
    @abstractmethod
    async def log_operation(self, message: BaseModel, user_id: str) -> None:
        ...

class AuditMiddleware(Middleware):
    """Log all commands and queries to an audit trail."""
    
    def __init__(self, audit_service: AuditService):  # (1)!
        self.audit_service = audit_service
    
    @intercepts
    async def audit_command(self, command: Command, next: Handler):
        user_id = get_current_user_id()
        await self.audit_service.log_operation(command, user_id)
        return await next(command)
    
    @intercepts
    async def audit_query(self, query: Query, next: Handler):
        user_id = get_current_user_id()
        await self.audit_service.log_operation(query, user_id)
        return await next(query)
```

1. `AuditService` is automatically injected by the DI container

Register the dependency and middleware:

```python
app = (
    ApplicationBuilder()
    .register_dependency(AuditService, DatabaseAuditService)
    .register_middleware(AuditMiddleware)
    .build()
)
```

## Intercepting Specific Message Types

The type annotation on the message parameter determines which messages the 
interceptor handles. You can intercept at different levels of specificity:

### All Commands

Annotate with the base `Command` type to intercept every command:

```python
@intercepts
async def intercept_all_commands(self, command: Command, next: Handler):
    # Runs for ALL commands
    return await next(command)
```

### All Queries

Annotate with the base `Query` type to intercept every query:

```python
@intercepts
async def intercept_all_queries(self, query: Query, next: Handler):
    # Runs for ALL queries
    return await next(query)
```

### Specific Message Type

Annotate with a specific type to intercept only that message:

```python
@intercepts
async def intercept_deposit(
    self, 
    command: DepositMoney,  # Only DepositMoney commands
    next: Handler
):
    if command.amount > 10000:
        await self.compliance_service.flag_large_deposit(command)
    return await next(command)

@intercepts
async def intercept_balance_query(
    self, 
    query: GetAccountBalance,  # Only GetAccountBalance queries
    next: Handler
) -> int:
    # Check if caller has permission to view this account
    if not self.can_view_account(query.account_id):
        raise PermissionError("Not authorized")
    return await next(query)
```

### Message Hierarchy

If you have a message hierarchy, you can intercept at any level:

```python
# Base class for all financial commands
class FinancialCommand(Command[None]):
    amount: int

class DepositMoney(FinancialCommand):
    ...

class WithdrawMoney(FinancialCommand):
    ...

class TransferMoney(FinancialCommand):
    from_account: UUID
    to_account: UUID

# Middleware that intercepts all financial commands
class FinancialComplianceMiddleware(Middleware):
    @intercepts
    async def check_compliance(
        self, 
        command: FinancialCommand,  # All DepositMoney, WithdrawMoney, TransferMoney
        next: Handler
    ):
        if command.amount > 10000:
            await self.report_to_compliance(command)
        return await next(command)
```

### Multiple Interceptors

A single middleware can have multiple interceptor methods for different types:

```python
class TransactionLimitsMiddleware(Middleware):
    @intercepts
    async def check_deposit_limit(
        self, 
        command: DepositMoney, 
        next: Handler
    ):
        if command.amount > 50000:
            raise DepositLimitExceeded(command.amount)
        return await next(command)
    
    @intercepts
    async def check_withdrawal_limit(
        self, 
        command: WithdrawMoney, 
        next: Handler
    ):
        if command.amount > 10000:
            raise WithdrawalLimitExceeded(command.amount)
        return await next(command)
```

## Understanding Middleware Order

Middleware executes in **registration order**. The first registered middleware 
is the **outermost** wrapper:

```python
app = (
    ApplicationBuilder()
    .register_middleware(LoggingMiddleware)      # Runs 1st (outermost)
    .register_middleware(AuthenticationMiddleware)  # Runs 2nd
    .register_middleware(ValidationMiddleware)   # Runs 3rd
    .register_aggregate(BankAccount)             # Command handler (innermost)
    .register_projection(AccountBalanceProjection)  # Query handler
    .build()
)
```

The execution flow looks like this:

```
Command → Logging → Authentication → Validation → Aggregate
                                                      ↓
Response ← Logging ← Authentication ← Validation ← Aggregate

Query → Logging → Authentication → Validation → Projection
                                                     ↓
Response ← Logging ← Authentication ← Validation ← Projection
```

### Order Matters

Consider these scenarios:

| Scenario | Recommended Order |
|----------|-------------------|
| Log all requests including failures | Logging **first** |
| Only log authenticated requests | Authentication **before** Logging |
| Validate before expensive auth check | Validation **before** Authentication |
| Retry after transient failures | Retry **outermost** (wraps everything) |
| Cache query results | Caching **outermost** for queries |

```python
# Retry wraps everything - retries the whole chain on failure
app = (
    ApplicationBuilder()
    .register_middleware(RetryMiddleware)        # Outermost - retries everything
    .register_middleware(CachingMiddleware)      # Cache query results
    .register_middleware(LoggingMiddleware)      # Logs each attempt
    .register_middleware(AuthenticationMiddleware)
    .register_middleware(ValidationMiddleware)
    .build()
)
```

## Common Middleware Patterns

### Caching Queries

Cache query results to improve performance:

```python
class QueryCachingMiddleware(Middleware):
    """Cache query results."""
    
    def __init__(self):
        self.cache: dict[str, Any] = {}
    
    @intercepts
    async def cache_queries(self, query: Query, next: Handler):
        cache_key = f"{type(query).__name__}:{query.model_dump_json()}"
        
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        result = await next(query)
        self.cache[cache_key] = result
        return result
```

### Authorization

Check permissions for both commands and queries:

```python
class AuthorizationMiddleware(Middleware):
    """Enforce authorization rules."""
    
    def __init__(self, auth_service: AuthService):
        self.auth_service = auth_service
    
    @intercepts
    async def authorize_command(self, command: Command, next: Handler):
        user = get_current_user()
        if not self.auth_service.can_execute(user, command):
            raise PermissionError(f"Not authorized: {type(command).__name__}")
        return await next(command)
    
    @intercepts
    async def authorize_query(self, query: Query, next: Handler):
        user = get_current_user()
        if not self.auth_service.can_read(user, query):
            raise PermissionError(f"Not authorized: {type(query).__name__}")
        return await next(query)
```

### Rate Limiting

Throttle requests to protect resources:

```python
class RateLimitMiddleware(Middleware):
    """Rate limit commands and queries."""
    
    def __init__(self, limiter: RateLimiter):
        self.limiter = limiter
    
    @intercepts
    async def rate_limit(self, message: BaseModel, next: Handler):
        user = get_current_user()
        if not await self.limiter.allow(user.id):
            raise RateLimitExceeded()
        return await next(message)
```

## When to Use Middleware

Middleware is ideal for **cross-cutting concerns** that apply to many operations. 
However, not every problem requires middleware.

### Use Middleware For

| Concern | Example |
|---------|---------|
| **Logging/Tracing** | Log all operations with correlation IDs |
| **Authentication** | Verify user identity before processing |
| **Authorization** | Check permissions for message types |
| **Validation** | Apply business rules across messages |
| **Rate Limiting** | Throttle request frequency |
| **Metrics** | Track latency and counts |
| **Retry Logic** | Handle transient failures |
| **Idempotency** | Prevent duplicate command processing |
| **Caching** | Cache query results |

### Don't Use Middleware For

| Concern | Better Alternative |
|---------|-------------------|
| **Domain logic** | Put it in the aggregate's command handler |
| **Single-message behavior** | Handle in the specific handler |
| **Event reactions** | Use an Event Processor |
| **Multi-aggregate coordination** | Use a Saga |
| **Read model updates** | Use a Projection |

### Decision Guide

```
Is this concern...
    └─ Specific to one message type?
        └─ Yes → Handle in the aggregate/projection
        └─ No → Could be middleware
            └─ Does it need aggregate/projection state?
                └─ Yes → Handle in the aggregate/projection
                └─ No → Middleware is appropriate
```

## Built-in Middleware

Interlock provides several middleware out of the box:

| Middleware | Purpose |
|------------|---------|
| `LoggingMiddleware` | Log operations with correlation context |
| `IdempotencyMiddleware` | Prevent duplicate command processing |
| `ConcurrencyRetryMiddleware` | Retry on optimistic concurrency conflicts |
| `ContextPropagationMiddleware` | Propagate correlation/causation IDs |

```python
from interlock.application.middleware import (
    LoggingMiddleware,
    IdempotencyMiddleware,
    ConcurrencyRetryMiddleware,
    ContextPropagationMiddleware,
)

app = (
    ApplicationBuilder()
    .register_middleware(ContextPropagationMiddleware)
    .register_middleware(LoggingMiddleware)
    .register_middleware(IdempotencyMiddleware)
    .register_middleware(ConcurrencyRetryMiddleware)
    .build()
)
```

## Testing Middleware

Test middleware by building an application with your middleware and stub 
dependencies:

```python
import pytest
from interlock.application import ApplicationBuilder

class StubAuditService(AuditService):
    def __init__(self):
        self.logged_operations = []
    
    async def log_operation(self, message: BaseModel, user_id: str) -> None:
        self.logged_operations.append((message, user_id))

@pytest.fixture
def app_with_audit():
    stub = StubAuditService()
    return (
        ApplicationBuilder()
        .register_aggregate(BankAccount)
        .register_projection(AccountBalanceProjection)
        .register_dependency(AuditService, lambda: stub)
        .register_middleware(AuditMiddleware)
        .build()
    ), stub

@pytest.mark.asyncio
async def test_audit_middleware_logs_commands(app_with_audit):
    app, stub = app_with_audit
    
    async with app:
        await app.dispatch(DepositMoney(aggregate_id=uuid4(), amount=100))
    
    assert len(stub.logged_operations) == 1
    assert isinstance(stub.logged_operations[0][0], DepositMoney)

@pytest.mark.asyncio
async def test_audit_middleware_logs_queries(app_with_audit):
    app, stub = app_with_audit
    account_id = uuid4()
    
    async with app:
        # Set up account first
        await app.dispatch(OpenAccount(aggregate_id=account_id, owner="Test"))
        
        # Query should be logged
        await app.query(GetAccountBalance(account_id=account_id))
    
    # One command + one query logged
    assert len(stub.logged_operations) == 2
    assert isinstance(stub.logged_operations[1][0], GetAccountBalance)
```

## Summary

| Concept | Description |
|---------|-------------|
| `Middleware` | Base class for middleware |
| `@intercepts` | Decorator marking interceptor methods |
| Type annotation | Determines which commands/queries are intercepted |
| `next(message)` | Continues to the next handler in the chain |
| Registration order | First registered = outermost wrapper |

## Next Steps

- [Tutorial: Middleware](../tutorial/06-middleware.md) — Hands-on middleware example
- [Commands](../concepts/commands.md) — Write operations
- [Queries](../concepts/queries.md) — Read operations
- [API Reference](../reference/index.md) — Complete API documentation
