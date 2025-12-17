# Dependency Injection

Interlock uses **dependency injection (DI)** to wire up your application components. This guide explains how DI works and how to use it effectively.

## What is Dependency Injection?

Dependency injection is a pattern where objects receive their dependencies from an external source rather than creating them internally:

```python
# Without DI - tightly coupled
class AccountBalanceProjection:
    def __init__(self):
        self.repository = PostgresBalanceRepository()  # Hard-coded!

# With DI - loosely coupled
class AccountBalanceProjection:
    def __init__(self, repository: BalanceRepository):
        self.repository = repository  # Injected!
```

Benefits:

- **Testability**: Swap real implementations for test doubles
- **Flexibility**: Change implementations without modifying consumers
- **Explicit dependencies**: Easy to see what a class needs

## How Interlock DI Works

Interlock uses **constructor injection** with **type hints**. When you register a component, Interlock inspects its `__init__` signature and resolves dependencies automatically:

```python
class AccountBalanceProjection(EventProcessor):
    def __init__(self, repository: BalanceRepository):  # Type hint
        self.repository = repository
```

When Interlock creates `AccountBalanceProjection`, it:

1. Inspects the constructor signature
2. Finds `repository: BalanceRepository`
3. Looks up the registered implementation for `BalanceRepository`
4. Creates and injects that implementation

## Registering Dependencies

Use `register_dependency()` to tell Interlock how to create instances:

```python
from interlock.application import ApplicationBuilder

app = (
    ApplicationBuilder()
    .register_dependency(BalanceRepository, PostgresBalanceRepository)
    .build()
)
```

### Interface and Implementation

The most common pattern registers an abstract base class (interface) with a concrete implementation:

```python
from abc import ABC, abstractmethod

# Interface
class EmailService(ABC):
    @abstractmethod
    async def send(self, to: str, subject: str, body: str) -> None: ...

# Implementation
class SendGridEmailService(EmailService):
    def __init__(self, api_key: str):
        self.api_key = api_key
    
    async def send(self, to: str, subject: str, body: str) -> None:
        # Send via SendGrid API
        ...

# Registration
app = (
    ApplicationBuilder()
    .register_dependency(EmailService, SendGridEmailService)
    .build()
)
```

Now any component requesting `EmailService` receives a `SendGridEmailService` instance.

### Self-Registration

If no factory is provided, the type is used directly:

```python
# These are equivalent:
.register_dependency(MyService, MyService)
.register_dependency(MyService)
```

### Factory Functions

For complex initialization, use a factory function:

```python
def create_email_service() -> EmailService:
    api_key = os.environ["SENDGRID_API_KEY"]
    return SendGridEmailService(api_key)

app = (
    ApplicationBuilder()
    .register_dependency(EmailService, create_email_service)
    .build()
)
```

Factory functions can also receive dependencies:

```python
def create_notification_service(
    email: EmailService,  # Injected!
    config: AppConfig     # Injected!
) -> NotificationService:
    return NotificationService(email, config.notification_settings)

app = (
    ApplicationBuilder()
    .register_dependency(EmailService, SendGridEmailService)
    .register_dependency(AppConfig)
    .register_dependency(NotificationService, create_notification_service)
    .build()
)
```

### Lambda Factories

For simple cases, use lambdas:

```python
app = (
    ApplicationBuilder()
    .register_dependency(
        EmailService, 
        lambda: SendGridEmailService(os.environ["API_KEY"])
    )
    .build()
)
```

## Where DI is Used

### Event Processors

Event processors commonly need repositories, services, or clients:

```python
class AccountBalanceProjection(EventProcessor):
    def __init__(self, repository: BalanceRepository):
        self.repository = repository
    
    @handles_event
    async def on_deposit(self, event: MoneyDeposited) -> None:
        current = self.repository.get_balance(event.account_id)
        self.repository.set_balance(event.account_id, current + event.amount)

# Register the processor and its dependency
app = (
    ApplicationBuilder()
    .register_dependency(BalanceRepository, InMemoryBalanceRepository)
    .register_event_processor(AccountBalanceProjection)
    .build()
)
```

### Middleware

Middleware can inject services for cross-cutting concerns:

```python
class FraudDetectionMiddleware(CommandMiddleware):
    def __init__(self, fraud_service: FraudService):
        self.fraud_service = fraud_service
    
    @intercepts
    async def check_fraud(self, command: DepositMoney, next: CommandHandler) -> None:
        if await self.fraud_service.is_suspicious(command):
            raise FraudDetectedError("Transaction flagged")
        await next(command)

app = (
    ApplicationBuilder()
    .register_dependency(FraudService, MLFraudService)
    .register_middleware(FraudDetectionMiddleware)
    .build()
)
```

### Sagas

Sagas often need to dispatch commands or access external services:

```python
class MoneyTransferSaga(Saga[TransferState]):
    def __init__(self, state_store: SagaStateStore, command_bus: CommandBus):
        super().__init__(state_store)
        self.command_bus = command_bus
    
    @saga_step
    async def on_transfer_initiated(self, event: TransferInitiated) -> TransferState:
        await self.command_bus.dispatch(
            WithdrawMoney(aggregate_id=event.from_account, amount=event.amount)
        )
        return TransferState(...)
```

### Event Upcasters

Upcasters can inject services for async data enrichment:

```python
class MoneyDepositedV1ToV2(EventUpcaster[MoneyDepositedV1, MoneyDepositedV2]):
    def __init__(self, account_service: AccountLookupService):
        self.account_service = account_service
    
    async def upcast_payload(self, data: MoneyDepositedV1) -> MoneyDepositedV2:
        email = await self.account_service.get_email(data.account_id)
        return MoneyDepositedV2(amount=data.amount, email=email)
```

## Resolving Dependencies Manually

Use `app.resolve()` to get instances directly:

```python
async with app:
    email_service = app.resolve(EmailService)
    await email_service.send("user@example.com", "Hello", "Welcome!")
```

This is useful for:

- Integration tests that need to verify service state
- Manual service access outside the normal flow
- Debugging

## Singleton Behavior

All registered dependencies are **singletons** within the application. The same instance is returned for every resolution:

```python
app = ApplicationBuilder().register_dependency(EmailService, SendGridEmailService).build()

async with app:
    service1 = app.resolve(EmailService)
    service2 = app.resolve(EmailService)
    assert service1 is service2  # Same instance!
```

## Testing with DI

DI makes testing straightforward—swap real implementations for test doubles:

```python
import pytest
from interlock.application import ApplicationBuilder

# Test double
class StubEmailService(EmailService):
    def __init__(self):
        self.sent_emails = []
    
    async def send(self, to: str, subject: str, body: str) -> None:
        self.sent_emails.append((to, subject, body))

@pytest.fixture
def app():
    return (
        ApplicationBuilder()
        .register_dependency(EmailService, StubEmailService)
        .register_event_processor(NotificationProcessor)
        .build()
    )

async def test_sends_notification_email(app):
    async with app:
        # Trigger event processing...
        
        # Verify via the stub
        email_service = app.resolve(EmailService)
        assert len(email_service.sent_emails) == 1
        assert email_service.sent_emails[0][1] == "Order Confirmed"
```

### Using Scenario Helpers

Interlock's test scenarios automatically use the registered dependencies:

```python
@pytest.fixture
def app():
    return (
        ApplicationBuilder()
        .register_dependency(BalanceRepository, InMemoryBalanceRepository)
        .register_event_processor(AccountBalanceProjection)
        .build()
    )

async def test_projection_updates_balance(app):
    async with app.processor_scenario(AccountBalanceProjection) as scenario:
        scenario \
            .given(MoneyDeposited(account_id=account_id, amount=100)) \
            .should_have_state(
                lambda p: p.repository.get_balance(account_id) == 100
            )
```

## Common Patterns

### Configuration Objects

Use Pydantic settings for configuration:

```python
from pydantic_settings import BaseSettings

class AppConfig(BaseSettings):
    database_url: str
    redis_url: str
    sendgrid_api_key: str
    
    model_config = {"env_prefix": "APP_"}

app = (
    ApplicationBuilder()
    .register_dependency(AppConfig)  # Reads from environment
    .register_dependency(EmailService, lambda config: SendGridEmailService(config.sendgrid_api_key))
    .build()
)
```

### Layered Dependencies

Build complex dependency graphs:

```python
app = (
    ApplicationBuilder()
    # Infrastructure layer
    .register_dependency(DatabasePool, create_db_pool)
    .register_dependency(RedisClient, create_redis_client)
    
    # Repository layer
    .register_dependency(AccountRepository, PostgresAccountRepository)
    .register_dependency(TransactionRepository, PostgresTransactionRepository)
    
    # Service layer
    .register_dependency(AccountService, DefaultAccountService)
    .register_dependency(FraudService, MLFraudService)
    
    # Application layer
    .register_event_processor(AccountBalanceProjection)
    .register_middleware(FraudDetectionMiddleware)
    .build()
)
```

### Environment-Specific Registration

Swap implementations based on environment:

```python
import os

builder = ApplicationBuilder()

if os.environ.get("ENV") == "production":
    builder.register_dependency(EmailService, SendGridEmailService)
    builder.register_dependency(FraudService, MLFraudService)
else:
    builder.register_dependency(EmailService, ConsoleEmailService)
    builder.register_dependency(FraudService, NoOpFraudService)

app = builder.build()
```

## Best Practices

### Depend on Abstractions

Prefer abstract base classes over concrete implementations:

```python
# Good - depends on abstraction
def __init__(self, repository: BalanceRepository): ...

# Avoid - depends on concrete class
def __init__(self, repository: PostgresBalanceRepository): ...
```

### Keep Constructors Simple

Constructors should only assign dependencies, not perform logic:

```python
# Good
def __init__(self, service: EmailService):
    self.service = service

# Avoid - logic in constructor
def __init__(self, api_key: str):
    self.service = EmailService(api_key)
    self.service.connect()  # Side effect!
```

### Use Factory Functions for Complex Setup

When initialization is complex, extract it to a factory:

```python
def create_database_pool(config: AppConfig) -> DatabasePool:
    pool = DatabasePool(
        host=config.db_host,
        port=config.db_port,
        user=config.db_user,
        password=config.db_password,
    )
    pool.set_max_connections(config.db_max_connections)
    return pool

app = (
    ApplicationBuilder()
    .register_dependency(AppConfig)
    .register_dependency(DatabasePool, create_database_pool)
    .build()
)
```

## Further Reading

- [Application Lifecycle](application-lifecycle.md) — Startup/shutdown with DI
- [Writing Tests](writing-tests.md) — Testing with dependency injection
- [Custom Middleware](custom-middleware.md) — Middleware with injected services

