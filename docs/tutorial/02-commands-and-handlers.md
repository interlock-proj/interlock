# Commands & Handlers

Commands represent intent to change the system. 
In this section, you'll learn how to define commands and handle them in your aggregates.

## What is a Command?

A **command** is a message that expresses an intent to perform an action. Commands are:

- Conventionally named in imperative form (e.g., `CreateAccount`, `DepositMoney`)
- Handled by exactly one aggregate
- Generally contain no logic themselves (Data Class style)

## Defining Commands

Commands, like aggregates, are pydantic models. 

```python
from interlock.domain import Command

class CreateAccount(Command):
    owner_name: str

class DepositMoney(Command):
    amount: int
```

When inheriting from the `Command` base class, you will automatically inherit an `aggregate_id` field.
to identify the aggregate that should handle the command. 
This is used by the framework to route the command to the appropriate aggregate. 
There are other fields that are automatically inherited from the `Command` base class that you can use to add more metadata to the command.
We'll cover these in a later section.

## Writing Tests for Our Command Handling

```python
# tests/aggregates/test_bank_account.py
def test_deposit_money_increases_balance():
    account = BankAccount()
    account.handle(DepositMoney(aggregate_id=account.id, amount=50))
    assert account.balance.amount == 50
```

In this test, we're using the `handle` method to test the execution of a command.
The `handle` method routes the command to the appropriate handler method via type annotations. 
This means that if the command is not handled by the aggregate, the test will fail.

!!! note "Commands require an aggregate_id"
    Every command needs an `aggregate_id` to identify which aggregate instance handles it.
    In tests, we use `account.id` to get the aggregate's auto-generated ID.


## Handling Commands in Aggregates

Now that we have our test, lets crack open the aggregate and add the command handler.

```python hl_lines="2-3 8-10 18-21"
from pydantic import BaseModel, Field 
from interlock.domain import Aggregate
from interlock.routing import handles_command  # (1)!

class Balance(BaseModel):
    amount: int = 0
    currency: str = "USD"

    def increase(self, amount: int) -> None:  # (2)!
        self.amount += amount

    def is_atleast(self, amount: int) -> bool:
        return self.amount >= amount

class BankAccount(Aggregate):
    balance: Balance = Field(default_factory=Balance)
    is_active: bool = True

    @handles_command  # (3)!
    def handle_deposit_money(self, command: DepositMoney) -> None:
        self.balance.increase(command.amount)  # THIS IS WRONG! We'll fix this in the next section.

    def has_sufficient_balance(self, amount: int) -> bool:
        return self.balance.is_atleast(amount)
```

1. Import the `handles_command` decorator
2. Add a method to mutate the balance
3. Decorate command handler methods with `@handles_command`

!!! danger "Wait, This Handler is Wrong!"
    Look closely at line 20—we're directly mutating `self.balance`. 
    This works for our test, but it **breaks event sourcing**.
    
    If we directly mutate state, we lose the history of *what happened*. 
    We can't replay events to rebuild state, we can't audit changes, and we can't 
    project events to other systems.
    
    In the next section, we'll fix this by introducing **events**.

## Command Handler Discovery

Interlock discovers command handlers via the `@handles_command` decorator and type annotations.
Common naming conventions (not required, but recommended):

| Command | Handler Method |
|---------|---------------|
| `CreateAccount` | `handle_create_account` |
| `DepositMoney` | `handle_deposit_money` |

## Next Steps

Our command handler works, but it's not event-sourced. 
Let's [fix this with events](03-events-and-sourcing.md).

