# Custom Middleware

Build custom middleware to handle cross-cutting concerns in your application.

## Goal

Create middleware that intercepts command execution for logging, validation, 
authorization, and more.

## Prerequisites

- Understanding of [Commands](../concepts/commands.md)
- Familiarity with the [Tutorial: Middleware](../tutorial/05-middleware.md)

## What is Middleware?

Middleware wraps command execution in a chain, allowing you to:

- Execute code **before** the command reaches its handler
- Execute code **after** the command has been handled
- **Short-circuit** execution (reject commands, return early)
- **Transform** commands before they're handled
- Handle **exceptions** from downstream handlers

## Creating Custom Middleware

Middleware extends `CommandMiddleware` and uses the `@intercepts` decorator to 
mark interceptor methods:

```python
from interlock.application.commands import CommandMiddleware, CommandHandler
from interlock.routing import intercepts
from interlock.domain import Command

class TimingMiddleware(CommandMiddleware):
    """Measure and log command execution time."""

    @intercepts
    async def time_command(
        self, 
        command: Command,  # (1)!
        next: CommandHandler  # (2)!
    ) -> None:
        import time
        
        start = time.perf_counter()
        try:
            await next(command)  # (3)!
        finally:
            elapsed = time.perf_counter() - start
            print(f"{type(command).__name__} completed in {elapsed:.3f}s")
```

1. Type annotation determines which commands are intercepted
2. `next` is the next handler in the chain (middleware or aggregate)
3. Call `await next(command)` to continue the chain

## Dependency Injection

Middleware constructors support dependency injection. Dependencies are resolved 
from the DI container when the middleware is instantiated:

```python
from abc import ABC, abstractmethod

class AuditService(ABC):
    @abstractmethod
    async def log_command(self, command: Command, user_id: str) -> None:
        ...

class AuditMiddleware(CommandMiddleware):
    """Log all commands to an audit trail."""
    
    def __init__(self, audit_service: AuditService):  # (1)!
        self.audit_service = audit_service
    
    @intercepts
    async def audit_command(
        self, 
        command: Command, 
        next: CommandHandler
    ) -> None:
        user_id = get_current_user_id()
        await self.audit_service.log_command(command, user_id)
        await next(command)
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

## Intercepting Specific Command Types

The type annotation on the `command` parameter determines which commands the 
interceptor handles. You can intercept at different levels of specificity:

### All Commands

Annotate with the base `Command` type to intercept every command:

```python
@intercepts
async def intercept_all(self, command: Command, next: CommandHandler) -> None:
    # Runs for ALL commands
    await next(command)
```

### Specific Command Type

Annotate with a specific command type to intercept only that command:

```python
@intercepts
async def intercept_deposit(
    self, 
    command: DepositMoney,  # Only DepositMoney commands
    next: CommandHandler
) -> None:
    if command.amount > 10000:
        await self.compliance_service.flag_large_deposit(command)
    await next(command)
```

### Command Hierarchy

If you have a command hierarchy, you can intercept at any level:

```python
# Base class for all financial commands
class FinancialCommand(Command):
    amount: int

class DepositMoney(FinancialCommand):
    ...

class WithdrawMoney(FinancialCommand):
    ...

class TransferMoney(FinancialCommand):
    from_account: ULID
    to_account: ULID

# Middleware that intercepts all financial commands
class FinancialComplianceMiddleware(CommandMiddleware):
    @intercepts
    async def check_compliance(
        self, 
        command: FinancialCommand,  # All DepositMoney, WithdrawMoney, TransferMoney
        next: CommandHandler
    ) -> None:
        if command.amount > 10000:
            await self.report_to_compliance(command)
        await next(command)
```

### Multiple Interceptors

A single middleware can have multiple interceptor methods for different command types:

```python
class TransactionLimitsMiddleware(CommandMiddleware):
    @intercepts
    async def check_deposit_limit(
        self, 
        command: DepositMoney, 
        next: CommandHandler
    ) -> None:
        if command.amount > 50000:
            raise DepositLimitExceeded(command.amount)
        await next(command)
    
    @intercepts
    async def check_withdrawal_limit(
        self, 
        command: WithdrawMoney, 
        next: CommandHandler
    ) -> None:
        if command.amount > 10000:
            raise WithdrawalLimitExceeded(command.amount)
        await next(command)
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
    .register_aggregate(BankAccount)             # Handler (innermost)
    .build()
)
```

The execution flow looks like this:

```
Request → Logging → Authentication → Validation → Handler
                                                      ↓
Response ← Logging ← Authentication ← Validation ← Handler
```

### Order Matters

Consider these scenarios:

| Scenario | Recommended Order |
|----------|-------------------|
| Log all requests including failures | Logging **first** |
| Only log authenticated requests | Authentication **before** Logging |
| Validate before expensive auth check | Validation **before** Authentication |
| Retry after transient failures | Retry **outermost** (wraps everything) |

```python
# Retry wraps everything - retries the whole chain on failure
app = (
    ApplicationBuilder()
    .register_middleware(RetryMiddleware)        # Outermost - retries everything
    .register_middleware(LoggingMiddleware)      # Logs each attempt
    .register_middleware(AuthenticationMiddleware)
    .register_middleware(ValidationMiddleware)
    .build()
)
```

## When to Use Middleware

Middleware is ideal for **cross-cutting concerns** that apply to many commands. 
However, not every problem requires middleware.

### Use Middleware For

| Concern | Example |
|---------|---------|
| **Logging/Tracing** | Log all commands with correlation IDs |
| **Authentication** | Verify user identity before processing |
| **Authorization** | Check permissions for command types |
| **Validation** | Apply business rules across commands |
| **Rate Limiting** | Throttle command frequency |
| **Metrics** | Track command latency and counts |
| **Retry Logic** | Handle transient failures |
| **Idempotency** | Prevent duplicate processing |

### Don't Use Middleware For

| Concern | Better Alternative |
|---------|-------------------|
| **Domain logic** | Put it in the aggregate's command handler |
| **Single-command behavior** | Handle in the specific aggregate |
| **Event reactions** | Use an Event Processor |
| **Multi-aggregate coordination** | Use a Saga |
| **Read model updates** | Use an Event Processor (projection) |

### Decision Guide

```
Is this concern...
    └─ Specific to one command type?
        └─ Yes → Handle in the aggregate
        └─ No → Could be middleware
            └─ Does it need aggregate state?
                └─ Yes → Handle in the aggregate
                └─ No → Middleware is appropriate
```

## Built-in Middleware

Interlock provides several middleware out of the box:

| Middleware | Purpose |
|------------|---------|
| `LoggingMiddleware` | Log commands with correlation context |
| `IdempotencyMiddleware` | Prevent duplicate command processing |
| `ConcurrencyRetryMiddleware` | Retry on optimistic concurrency conflicts |
| `ContextPropagationMiddleware` | Propagate correlation/causation IDs |

```python
from interlock.application.commands.middleware import (
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
        self.logged_commands = []
    
    async def log_command(self, command: Command, user_id: str) -> None:
        self.logged_commands.append((command, user_id))

@pytest.fixture
def app_with_audit():
    stub = StubAuditService()
    return (
        ApplicationBuilder()
        .register_aggregate(BankAccount)
        .register_dependency(AuditService, lambda: stub)
        .register_middleware(AuditMiddleware)
        .build()
    ), stub

@pytest.mark.asyncio
async def test_audit_middleware_logs_commands(app_with_audit):
    app, stub = app_with_audit
    
    async with app:
        await app.dispatch(DepositMoney(aggregate_id=ULID(), amount=100))
    
    assert len(stub.logged_commands) == 1
    assert isinstance(stub.logged_commands[0][0], DepositMoney)
```

## Summary

| Concept | Description |
|---------|-------------|
| `CommandMiddleware` | Base class for middleware |
| `@intercepts` | Decorator marking interceptor methods |
| Type annotation | Determines which commands are intercepted |
| `next(command)` | Continues to the next handler in the chain |
| Registration order | First registered = outermost wrapper |

## Next Steps

- [Tutorial: Middleware](../tutorial/05-middleware.md) — Hands-on middleware example
- [API Reference](../reference/index.md) — Complete API documentation
