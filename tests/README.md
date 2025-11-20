# Test Suite Documentation

## Overview

This test suite has been refactored to follow best practices with:
- **Function-based tests** instead of class-based tests
- **Centralized fixtures** in `tests/conftest.py`
- **Base test application** that can be customized per test
- **Effective use of pytest fixtures**

## Architecture

### Central Fixtures (`tests/conftest.py`)

The `conftest.py` file provides a comprehensive set of reusable fixtures:

#### Base Test Components
- **Commands**: `IncrementCounter`, `SetName`, `DepositMoney`, `WithdrawMoney`, `OpenAccount`
- **Events**: `CounterIncremented`, `NameChanged`, `MoneyDeposited`, `MoneyWithdrawn`, `AccountOpened`
- **Aggregates**: `Counter`, `BankAccount`
- **Infrastructure**: `ExecutionTracker` (custom test middleware)
  - Uses the existing `InMemoryEventStore` from `ouroboros.events.store`

#### Fixture Categories

**ID Fixtures**:
- `aggregate_id()` - Generate unique aggregate IDs
- `account_id()` - Generate unique account IDs (alias)
- `correlation_id()` - Generate unique correlation IDs

**Aggregate Fixtures**:
- `counter(aggregate_id)` - Counter aggregate instance
- `bank_account(aggregate_id)` - BankAccount aggregate instance

**Repository Fixtures**:
- `counter_repository(counter)` - Simple Counter repository
- `bank_account_repository(bank_account)` - Simple BankAccount repository

**Infrastructure Fixtures**:
- `event_store()` - In-memory event store
- `event_transport()` - In-memory event transport
- `saga_state_store()` - In-memory saga state store
- `execution_tracker()` - Command execution tracker

**Application Builder Fixtures**:
- `base_app_builder()` - Base ApplicationBuilder with common dependencies
- `counter_app()` - Pre-configured Counter application
- `bank_account_app()` - Pre-configured BankAccount application

#### Auto-cleanup
- `clear_execution_context` - Automatically clears execution context after each test

## Usage Examples

### Using Base Application Builder

Tests can extend the base application builder to add specific components:

```python
def test_something(base_app_builder, aggregate_id):
    """Test custom application configuration."""
    app = (
        base_app_builder
        .add_aggregate(Counter)
        .add_command(IncrementCounter)
        .use_synchronous_processing()
        .build()
    )

    await app.dispatch(IncrementCounter(aggregate_id=aggregate_id))
    # ... assertions
```

### Using Pre-configured Apps

For simple tests, use pre-configured application fixtures:

```python
def test_counter(counter_app, aggregate_id):
    """Test using pre-configured counter app."""
    await counter_app.dispatch(
        IncrementCounter(aggregate_id=aggregate_id, amount=5)
    )
    # ... assertions
```

### Using Individual Fixtures

Tests can compose fixtures for fine-grained control:

```python
def test_repository(counter_repository, aggregate_id, counter):
    """Test using individual fixtures."""
    async with counter_repository.acquire(aggregate_id) as agg:
        assert agg.id == aggregate_id
```

## Test Organization

### Unit Tests (`tests/unit/`)
- Focus on testing individual components in isolation
- Use mocks and fixtures to isolate dependencies
- Fast execution, no external dependencies

### Integration Tests (`tests/integration/`)
- Test component interactions
- May use real implementations (in-memory versions)
- Test end-to-end workflows

## Best Practices

### 1. Function-Based Tests
All tests are implemented as functions, not classes. This makes them more composable and easier to understand.

**Good**:
```python
def test_something(fixture):
    assert fixture.value == expected
```

**Avoid**:
```python
class TestSomething:
    def test_method(self, fixture):
        assert fixture.value == expected
```

### 2. Descriptive Test Names
Test names should clearly describe what they test:

```python
def test_correlation_id_propagates_to_events():
    """Correlation ID should propagate from command to events."""
    # ...
```

### 3. Use Fixtures Effectively
Leverage pytest fixtures for setup and teardown:

```python
@pytest.fixture
def custom_fixture(base_app_builder):
    """Create a custom fixture based on base builder."""
    return base_app_builder.add_aggregate(MyAggregate)
```

### 4. Test Isolation
Each test should be independent and not rely on state from other tests:
- Use fresh fixture instances
- Auto-cleanup is provided for execution context
- Avoid global state

### 5. Clear Assertions
Make assertions clear and specific:

```python
# Good - specific assertion
assert event.correlation_id == correlation_id

# Avoid - generic assertion
assert event is not None
```

## Extending the Test Suite

### Adding New Fixtures

Add common fixtures to `tests/conftest.py`:

```python
@pytest.fixture
def my_custom_aggregate(aggregate_id: UUID) -> MyAggregate:
    """Create a custom aggregate instance."""
    return MyAggregate(id=aggregate_id)
```

### Test-Specific Fixtures

For fixtures needed by a specific test file, add them in that file or a local `conftest.py`:

```python
# tests/unit/mymodule/conftest.py
@pytest.fixture
def module_specific_fixture():
    return SomeTestHelper()
```

### Customizing Base Application

Tests can modify the base application builder as needed:

```python
def test_with_custom_middleware(base_app_builder):
    """Test with custom middleware."""
    tracker = ExecutionTracker()

    app = (
        base_app_builder
        .add_aggregate(Counter)
        .add_command(IncrementCounter)
        .add_middleware(tracker, IncrementCounter)
        .build()
    )
    # ... test
```

## Common Patterns

### Testing Command Dispatch

```python
async def test_command_execution(counter_app, aggregate_id):
    command = IncrementCounter(aggregate_id=aggregate_id, amount=5)
    await counter_app.dispatch(command)
    # Verify state changes
```

### Testing Event Propagation

```python
async def test_event_propagation(base_app_builder):
    captured_events = []

    class EventCaptor(EventProcessor):
        @handles_event
        async def on_event(self, event: MyEvent):
            captured_events.append(event)

    app = (
        base_app_builder
        .add_event_processor(EventCaptor)
        # ... other setup
        .build()
    )

    # Dispatch command
    # Verify events were captured
    assert len(captured_events) == expected_count
```

### Testing with Correlation Tracking

```python
async def test_correlation(base_app_builder, correlation_id):
    app = (
        base_app_builder
        .use_correlation_tracking()
        .add_aggregate(BankAccount)
        .build()
    )

    command = OpenAccount(
        aggregate_id=uuid4(),
        owner="Alice",
        correlation_id=correlation_id
    )

    await app.dispatch(command)
    # Verify correlation propagation
```

## Troubleshooting

### Fixture Not Found
If a fixture is not found, ensure:
1. It's defined in `tests/conftest.py` or a local conftest
2. The fixture name matches exactly
3. Import statements are correct

### Async Test Issues
Use `@pytest.mark.asyncio` for async tests:

```python
@pytest.mark.asyncio
async def test_async_operation():
    result = await some_async_function()
    assert result == expected
```

### Context Not Clearing
The `clear_execution_context` fixture runs automatically. If you need manual control:

```python
from ouroboros.context import clear_context

def test_something():
    # test code
    clear_context()  # Manual cleanup if needed
```

## Test Statistics

After refactoring:
- **171 tests passing** (with some pre-existing failures unrelated to refactoring)
- All major test files converted to function-based tests
- Centralized fixtures reduce duplication
- Improved test maintainability and readability
