# Test Suite

This test suite follows pytest best practices with function-based tests, centralized fixtures, and clear separation between unit and integration tests.

## Directory Structure

```
tests/
├── conftest.py              # Central fixtures shared across all tests
├── fixtures/
│   └── test_app/            # Unified test application components
│       ├── aggregates/      # Test aggregates (BankAccount, Order)
│       ├── commands/        # Test commands
│       ├── middleware/      # Test middleware (ExecutionTracker)
│       ├── processors.py    # Event processors and sagas
│       └── services/        # Test services
├── unit/                    # Fast, isolated component tests
│   ├── conftest.py          # Unit-specific fixtures (if needed)
│   ├── application/         # Application layer tests
│   │   ├── aggregates/      # Repository, cache, snapshot tests
│   │   ├── commands/        # Command bus and middleware tests
│   │   ├── events/          # Event processing, upcasting tests
│   │   └── projections/     # Projection and query bus tests
│   ├── context/             # Execution context tests
│   ├── routing/             # Routing tests
│   └── testing/             # Testing utilities tests
└── integration/             # Tests with external dependencies
    ├── application/         # Cross-component integration tests
    ├── domain/              # Domain integration tests
    └── mongodb/             # MongoDB integration tests
```

## Central Fixtures

The `tests/conftest.py` file provides reusable fixtures for all tests.

### ID Fixtures

| Fixture | Description |
|---------|-------------|
| `aggregate_id` | Generates a unique UUID for aggregate identification |
| `account_id` | Alias for unique account IDs |
| `correlation_id` | Generates a unique correlation ID for tracing |

### Infrastructure Fixtures

| Fixture | Description |
|---------|-------------|
| `event_store` | In-memory event store instance |
| `event_transport` | In-memory event transport instance |
| `saga_state_store` | In-memory saga state store |
| `upcaster_map` | Empty UpcasterMap for testing upcasting |
| `execution_tracker` | Middleware that tracks command executions |

### Domain Fixtures

| Fixture | Description |
|---------|-------------|
| `bank_account` | BankAccount aggregate instance |
| `bank_account_repository` | Simple repository for BankAccount |

### Application Fixtures

| Fixture | Description |
|---------|-------------|
| `base_app_builder` | ApplicationBuilder with common dependencies pre-configured |
| `bank_account_app` | Application with BankAccount aggregate registered |
| `test_app` | Fully-configured app via convention-based discovery |
| `command_handler` | DelegateToAggregate resolved from bank account app |

### Auto-cleanup

The `clear_execution_context` fixture runs automatically after each test to reset the execution context.

## Test Application Components

The `tests/fixtures/test_app/` package provides a unified set of domain objects for testing:

- **Aggregates**: `BankAccount`, `Order`
- **Commands**: `OpenAccount`, `DepositMoney`, `WithdrawMoney`
- **Events**: Various banking events (deposited, withdrawn, etc.)
- **Processors**: `AccountStatisticsProcessor`, `MoneyTransferSaga`
- **Services**: `AuditService` with `IAuditService` interface
- **Middleware**: `ExecutionTracker`

## Writing Tests

### Basic Test Structure

```python
import pytest
from uuid import uuid4

@pytest.mark.asyncio
async def test_deposit_increases_balance(bank_account_app, aggregate_id):
    """Depositing money should increase the account balance."""
    from tests.fixtures.test_app import OpenAccount, DepositMoney

    async with bank_account_app:
        await bank_account_app.dispatch(OpenAccount(aggregate_id=aggregate_id, owner="Alice"))
        await bank_account_app.dispatch(DepositMoney(aggregate_id=aggregate_id, amount=100))
        # assertions...
```

### Using the Base Application Builder

Extend the base builder for custom configurations:

```python
@pytest.mark.asyncio
async def test_with_custom_middleware(base_app_builder, aggregate_id):
    """Test with custom middleware configuration."""
    from tests.fixtures.test_app import BankAccount, ExecutionTracker

    tracker = ExecutionTracker()
    app = (
        base_app_builder
        .register_aggregate(BankAccount)
        .register_middleware(tracker)
        .build()
    )

    async with app:
        # test code...
```

### Using Pre-configured Apps

For simpler tests, use the pre-configured application fixtures:

```python
@pytest.mark.asyncio
async def test_account_operations(bank_account_app, aggregate_id):
    """Test using pre-configured bank account app."""
    from tests.fixtures.test_app import OpenAccount

    async with bank_account_app:
        await bank_account_app.dispatch(OpenAccount(aggregate_id=aggregate_id, owner="Bob"))
```

### Adding Test-Specific Fixtures

For fixtures needed only in a specific test file or directory, add them to a local `conftest.py`:

```python
# tests/unit/mymodule/conftest.py
import pytest

@pytest.fixture
def custom_helper():
    """Fixture specific to this test module."""
    return SomeTestHelper()
```

## Best Practices

### 1. Use Function-Based Tests

Write tests as functions, not classes:

```python
# Preferred
@pytest.mark.asyncio
async def test_something(fixture):
    assert fixture.value == expected

# Avoid
class TestSomething:
    async def test_method(self, fixture):
        assert fixture.value == expected
```

### 2. Descriptive Test Names

Names should describe behavior being tested:

```python
async def test_withdraw_fails_when_insufficient_funds(bank_account_app, aggregate_id):
    """Withdrawal should fail when balance is insufficient."""
```

### 3. Test Isolation

Each test should be independent:

- Use fresh fixture instances per test
- Rely on `clear_execution_context` for automatic cleanup
- Avoid global state

### 4. Clear Assertions

Make assertions specific and descriptive:

```python
# Good
assert event.amount == 100
assert account.balance == expected_balance

# Avoid
assert event is not None
assert result
```

### 5. Mark Async Tests

Always mark async tests with `@pytest.mark.asyncio`:

```python
@pytest.mark.asyncio
async def test_async_operation():
    result = await some_async_function()
    assert result == expected
```

## Running Tests

Run all tests:

```bash
make test
# or
pytest
```

Run specific test categories:

```bash
pytest tests/unit -v          # Unit tests only
pytest tests/integration -v   # Integration tests only
```

Run tests matching a pattern:

```bash
pytest -k "bank_account"      # Tests with 'bank_account' in name
pytest tests/unit/application/commands/  # Specific directory
```

Run with coverage:

```bash
pytest --cov=interlock --cov-report=html
```

## Troubleshooting

### Fixture Not Found

Ensure the fixture is defined in:
1. `tests/conftest.py` (shared fixtures)
2. A local `conftest.py` in the test directory
3. The test file itself

### Async Test Not Running

Add the `@pytest.mark.asyncio` decorator:

```python
@pytest.mark.asyncio
async def test_something():
    ...
```

### Context State Leaking Between Tests

The `clear_execution_context` fixture runs automatically. For manual control:

```python
from interlock.context import clear_context

def test_something():
    # test code
    clear_context()  # Manual cleanup if needed
```
