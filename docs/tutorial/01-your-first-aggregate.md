# Your First Aggregate

In this section, you'll create your first aggregate—the core building block of event-sourced applications.

## What is an Aggregate?

An **aggregate** is a cluster of domain objects that are treated as a single unit for data changes. 
Aggregates are the core building blocks in Domain-Driven Design and Event Sourcing. They:

* Define **consistency boundaries**
* Encapsulate **business rules**
* Emit **events** when state changes
* Are loaded and saved as a **unit**

## Creating an Aggregate

The `Aggregate` base class is a actually a [Pydantic](https://docs.pydantic.dev/latest/) model.
This means it has all the features of a Pydantic model, including:

* Validation
* Serialization
* Deserialization
* Documentation
* Type hints

For now, we can focus on modeling the state of the aggregate.
Lets start by defining some expected behavior of the aggregate.

```python
# tests/aggregates/test_bank_account.py
def test_has_sufficient_balance_is_sufficient():
    balance = BankAccount(balance=100)
    assert balance.has_sufficient_balance(50)

def test_has_sufficient_balance_is_not_sufficient():
    balance = BankAccount(balance=100)
    assert not balance.has_sufficient_balance(150)
```

And now lets create a simple aggregate for a bank account:

```python
# my_app/aggregates/bank_account.py
from interlock.domain import Aggregate

class BankAccount(Aggregate):
    balance: int = 0
    is_active: bool = False

    def has_sufficient_balance(self, amount: int) -> bool:
        return self.balance >= amount
```

!!! info "Aggregates need starting state"
    Aggregates need a starting state to be created.
    When creating new aggregates, you need to provide a starting state. 
    In effect, this means that the aggregate needs to be constructable without passing an argument to the constructor.

In this case, we define a couple of fields that represent the state of the aggregate. 
Often, however, you will want to define a collection of more complicated objects that represent the state of the aggregate.
That can be done by combining multiple Pydantic models into a single aggregate.
For example, lets factor out the balance into a seperate model with a bit more complexity:

```python
from pydantic import BaseModel, Field
from interlock.domain import Aggregate

class Balance(BaseModel):
    amount: int = 0
    currency: str = "USD"

    def is_atleast(self, amount: int) -> bool:
        return self.amount >= amount

class BankAccount(Aggregate):
    balance: Balance = Field(default_factory=Balance)
    is_active: bool = True

    def has_sufficient_balance(self, amount: int) -> bool:
        return self.balance.is_atleast(amount)
```

!!! warning "Keep Aggregates Small"
    An aggregate should be the smallest possible unit that maintains consistency. 
    Large aggregates lead to contention and performance issues.

## Next Steps

Obviously, this aggregate isn't very useful yet.
Let's [add commands to trigger state changes](02-commands-and-handlers.md) to make it more useful.

