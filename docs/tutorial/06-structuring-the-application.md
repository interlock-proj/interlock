# Structuring Your Application

So far, we've been building our application imperatively—registering each aggregate, 
processor, and middleware by hand. This works great for learning, but as your 
application grows, it becomes tedious.

Interlock provides a **convention-based** approach that automatically discovers 
and registers components based on your project structure.

## The Imperative Approach (What We've Done)

Up to this point, we've been explicit about every registration:

```python
from interlock.application import ApplicationBuilder

app = (
    ApplicationBuilder()
    .register_aggregate(BankAccount)
    .register_dependency(AccountBalanceRepository, lambda: balance_repo)
    .register_dependency(FraudService, RandomFraudService)
    .register_event_processor(AccountBalanceProjection)
    .register_middleware(LoggingMiddleware)
    .register_middleware(FraudDetectionMiddleware)
    .build()
)
```

This is **explicit** and **testable**, but it doesn't scale well.

## Recommended Project Structure

Interlock's conventions expect a specific project layout:

```
my_bank_app/
├── __init__.py
├── aggregates/
│   ├── __init__.py
│   └── bank_account.py      # Contains BankAccount aggregate
├── events/
│   ├── __init__.py
│   └── account_events.py    # Contains MoneyDeposited, etc.
├── commands/
│   ├── __init__.py
│   └── account_commands.py  # Contains DepositMoney, etc.
├── processors/
│   ├── __init__.py
│   └── projections.py       # Contains AccountBalanceProjection
├── middleware/
│   ├── __init__.py
│   └── fraud.py             # Contains FraudDetectionMiddleware
└── services/
    ├── __init__.py
    └── fraud_service.py     # Contains FraudService implementations
```

## The Convention-Based Approach

With the right structure, you can use `convention_based()` to auto-discover components:

```python
from interlock.application import ApplicationBuilder

app = (
    ApplicationBuilder()
    .convention_based("my_bank_app")  # (1)!
    .build()
)
```

1. Scans `my_bank_app` and all submodules for aggregates, processors, middleware, etc.

The `convention_based()` method:

- Scans the package recursively
- Discovers classes that inherit from `Aggregate`, `EventProcessor`, `CommandMiddleware`
- Registers them automatically with the builder

## How Discovery Works

Interlock uses type introspection to find components:

| Base Class | Discovered From |
|------------|-----------------|
| `Aggregate` | Any module in the package |
| `EventProcessor` | Any module in the package |
| `CommandMiddleware` | Any module in the package |
| `EventUpcaster` | Any module in the package |

## Mixing Approaches

You can combine convention-based discovery with explicit registration:

```python
app = (
    ApplicationBuilder()
    .convention_based("my_bank_app")  # Auto-discover most things
    .register_dependency(FraudService, MLFraudService)  # Override for production
    .build()
)
```

This is useful when you want conventions for most things but need explicit 
control over certain dependencies (like swapping implementations for different environments).

## Testing with Conventions

For tests, you might want to use the imperative approach for isolation:

```python
# In tests, be explicit for control
def create_test_app():
    return (
        ApplicationBuilder()
        .register_aggregate(BankAccount)
        .register_dependency(FraudService, StubFraudService)
        .build()
    )
```

Or use conventions with test-specific overrides:

```python
def create_test_app():
    return (
        ApplicationBuilder()
        .convention_based("my_bank_app")
        .register_dependency(FraudService, StubFraudService)  # Test double
        .build()
    )
```

## Best Practices

1. **Start imperative**: When learning or prototyping, explicit registration is clearer
2. **Migrate to conventions**: As your app grows, switch to convention-based discovery
3. **Keep services explicit**: Dependencies like database connections should be explicit
4. **Use overrides**: Combine conventions with explicit registration for flexibility

## Next Steps

Finally, let's [put everything together](07-putting-it-together.md) into a complete application.

