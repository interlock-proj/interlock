# Writing Tests

Write effective, expressive tests for your event-sourced domain.

## Goal

Test aggregates, event processors, and sagas using Interlock's testing utilities.

## Prerequisites

- Familiarity with pytest
- Understanding of [Aggregates](../concepts/aggregates.md) and [Events](../concepts/events.md)

## Testing Philosophy

Event-sourced systems follow the **Given-When-Then** pattern naturally:

- **Given**: A sequence of past events
- **When**: A command is executed
- **Then**: Specific events are emitted (or errors raised)

## Aggregate Testing

Use `AggregateScenario` for behavior-driven aggregate tests:

```python
import pytest
from interlock.testing import AggregateScenario

@pytest.mark.asyncio
async def test_deposit_emits_event():
    async with AggregateScenario(BankAccount) as scenario:
        scenario \
            .given_no_events() \
            .when(DepositMoney(aggregate_id=scenario.aggregate_id, amount=100)) \
            .should_emit(MoneyDeposited)

@pytest.mark.asyncio
async def test_multiple_deposits():
    async with AggregateScenario(BankAccount) as scenario:
        scenario \
            .given(MoneyDeposited(amount=100)) \
            .when(DepositMoney(aggregate_id=scenario.aggregate_id, amount=50)) \
            .should_have_state(lambda acc: acc.balance.amount == 150)
```

The scenario automatically generates an `aggregate_id` accessible via `scenario.aggregate_id`.

## State Assertions

Check aggregate state after command execution:

```python
@pytest.mark.asyncio
async def test_balance_after_operations():
    async with AggregateScenario(BankAccount) as scenario:
        scenario \
            .given(MoneyDeposited(amount=100)) \
            .when(WithdrawMoney(aggregate_id=scenario.aggregate_id, amount=30)) \
            .should_emit(MoneyWithdrawn) \
            .should_have_state(lambda acc: acc.balance.amount == 70)
```

## Processor Testing

For processors with dependencies, use `app.processor_scenario()` to leverage DI:

```python
@pytest.mark.asyncio
async def test_projection_tracks_balance():
    app = (
        ApplicationBuilder()
        .register_dependency(AccountBalanceRepository, InMemoryAccountBalanceRepository)
        .register_event_processor(AccountBalanceProjection)
        .build()
    )
    
    async with app.processor_scenario(AccountBalanceProjection) as scenario:
        scenario \
            .given(MoneyDeposited(amount=100)) \
            .should_have_state(
                lambda p: p.repository.get_balance(scenario.aggregate_id) == 100
            )
```

For simple processors without dependencies, instantiate directly:

```python
from interlock.testing import ProcessorScenario

@pytest.mark.asyncio
async def test_simple_processor():
    async with ProcessorScenario(CountingProcessor()) as scenario:
        scenario \
            .given(SomeEvent()) \
            .should_have_state(lambda p: p.count == 1)
```

## Saga Testing

For sagas, use `app.saga_scenario()` for DI or instantiate with a state store:

```python
from interlock.application.events.processing import SagaStateStore
from interlock.testing import SagaScenario

@pytest.mark.asyncio
async def test_saga_state_transition():
    saga = OrderSaga(SagaStateStore.in_memory())
    
    async with SagaScenario(saga) as scenario:
        scenario \
            .given(OrderPlaced(saga_id="order-123")) \
            .should_have_state("order-123", lambda s: s.status == "placed")
```

## Best Practices

1. **Test behaviors, not implementation**: Focus on what events are emitted
2. **Use descriptive names**: `test_cannot_withdraw_more_than_balance`
3. **One scenario per test**: Keep tests focused
4. **Test edge cases**: Empty state, boundaries, error conditions
5. **Use DI for complex processors**: Build an app and use `app.processor_scenario()`

## Next Steps

- [Tutorial: Events & Sourcing](../tutorial/03-events-and-sourcing.md) - See TDD in action
- [API Reference](../reference/index.md)

