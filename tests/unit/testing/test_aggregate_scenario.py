from decimal import Decimal

import pytest
from ulid import ULID

from interlock.testing import AggregateScenario
from tests.fixtures.test_app import (
    BankAccount,
    DepositMoney,
    OpenAccount,
    WithdrawMoney,
)
from tests.fixtures.test_app.aggregates.bank_account import (
    AccountOpened,
    MoneyDeposited,
    MoneyWithdrawn,
)


@pytest.mark.asyncio
async def test_scenario_with_exact_payload_match():
    async with AggregateScenario(BankAccount) as scenario:
        scenario.given_no_events().when(
            OpenAccount(aggregate_id=scenario.aggregate_id, owner="Alice")
        ).should_emit(AccountOpened(owner="Alice"))


@pytest.mark.asyncio
async def test_scenario_with_type_match():
    async with AggregateScenario(BankAccount) as scenario:
        scenario.given_no_events().when(
            OpenAccount(aggregate_id=scenario.aggregate_id, owner="Bob")
        ).should_emit(AccountOpened)


@pytest.mark.asyncio
async def test_scenario_with_given_events():
    async with AggregateScenario(BankAccount) as scenario:
        scenario.given(
            AccountOpened(owner="Charlie"),
            MoneyDeposited(amount=Decimal("100.00")),
        ).when(
            WithdrawMoney(aggregate_id=scenario.aggregate_id, amount=Decimal("50.00"))
        ).should_emit(MoneyWithdrawn(amount=Decimal("50.00")))


@pytest.mark.asyncio
async def test_scenario_with_multiple_commands():
    async with AggregateScenario(BankAccount) as scenario:
        scenario.given(AccountOpened(owner="Dave")).when(
            DepositMoney(aggregate_id=scenario.aggregate_id, amount=Decimal("100.00")),
            DepositMoney(aggregate_id=scenario.aggregate_id, amount=Decimal("50.00")),
        ).should_emit(
            MoneyDeposited(amount=Decimal("100.00")),
            MoneyDeposited(amount=Decimal("50.00")),
        )


@pytest.mark.asyncio
async def test_scenario_expecting_error():
    async with AggregateScenario(BankAccount) as scenario:
        scenario.given_no_events().when(
            OpenAccount(aggregate_id=scenario.aggregate_id, owner="Eve"),
            OpenAccount(aggregate_id=scenario.aggregate_id, owner="Frank"),
        ).should_raise(ValueError)


@pytest.mark.asyncio
async def test_scenario_expecting_no_events():
    async with AggregateScenario(BankAccount) as scenario:
        scenario.given(AccountOpened(owner="Grace")).when(
            WithdrawMoney(aggregate_id=scenario.aggregate_id, amount=Decimal("100.00"))
        ).should_raise(ValueError).should_emit_nothing()


@pytest.mark.asyncio
async def test_scenario_without_context_manager():
    scenario = AggregateScenario(BankAccount)
    scenario.given_no_events().when(
        OpenAccount(aggregate_id=scenario.aggregate_id, owner="Henry")
    ).should_emit(AccountOpened)
    await scenario.execute_scenario()


@pytest.mark.asyncio
async def test_scenario_fails_when_expected_event_missing():
    with pytest.raises(AssertionError, match="should contain event of type"):
        async with AggregateScenario(BankAccount) as scenario:
            scenario.given_no_events().when(
                OpenAccount(aggregate_id=scenario.aggregate_id, owner="Iris")
            ).should_emit(MoneyDeposited)


@pytest.mark.asyncio
async def test_scenario_fails_when_expected_error_missing():
    with pytest.raises(AssertionError, match="should contain error of type"):
        async with AggregateScenario(BankAccount) as scenario:
            scenario.given_no_events().when(
                OpenAccount(aggregate_id=scenario.aggregate_id, owner="Jack")
            ).should_raise(ValueError)


@pytest.mark.asyncio
async def test_scenario_fails_when_events_emitted_unexpectedly():
    with pytest.raises(AssertionError, match="should not emit any events"):
        async with AggregateScenario(BankAccount) as scenario:
            scenario.given_no_events().when(
                OpenAccount(aggregate_id=scenario.aggregate_id, owner="Kate")
            ).should_emit_nothing()


@pytest.mark.asyncio
async def test_scenario_with_mixed_type_and_payload_expectations():
    async with AggregateScenario(BankAccount) as scenario:
        scenario.given(AccountOpened(owner="Leo")).when(
            DepositMoney(aggregate_id=scenario.aggregate_id, amount=Decimal("75.00")),
            WithdrawMoney(aggregate_id=scenario.aggregate_id, amount=Decimal("25.00")),
        ).should_emit(MoneyDeposited(amount=Decimal("75.00")), MoneyWithdrawn)


@pytest.mark.asyncio
async def test_scenario_handles_invalid_amount():
    async with AggregateScenario(BankAccount) as scenario:
        scenario.given(AccountOpened(owner="Mia")).when(
            DepositMoney(aggregate_id=scenario.aggregate_id, amount=Decimal("-10.00"))
        ).should_raise(ValueError).should_emit_nothing()


@pytest.mark.asyncio
async def test_scenario_handles_insufficient_funds():
    async with AggregateScenario(BankAccount) as scenario:
        scenario.given(
            AccountOpened(owner="Noah"),
            MoneyDeposited(amount=Decimal("50.00")),
        ).when(
            WithdrawMoney(aggregate_id=scenario.aggregate_id, amount=Decimal("100.00"))
        ).should_raise(ValueError).should_emit_nothing()


@pytest.mark.asyncio
async def test_scenario_chainable_api():
    scenario = AggregateScenario(BankAccount)
    scenario.given(AccountOpened(owner="Olivia")).given(
        MoneyDeposited(amount=Decimal("100.00"))
    ).when(DepositMoney(aggregate_id=scenario.aggregate_id, amount=Decimal("50.00"))).should_emit(
        MoneyDeposited(amount=Decimal("50.00"))
    )
    await scenario.execute_scenario()


@pytest.mark.asyncio
async def test_custom_id_works_with_context_manager():
    custom_id = ULID()
    async with AggregateScenario(BankAccount, aggregate_id=custom_id) as scenario:
        assert scenario.aggregate_id == custom_id
        scenario.when(OpenAccount(aggregate_id=scenario.aggregate_id, owner="Paula")).should_emit(
            AccountOpened(owner="Paula")
        )


def test_scenario_auto_generates_aggregate_id():
    scenario = AggregateScenario(BankAccount)
    assert scenario.aggregate_id is not None
    assert isinstance(scenario.aggregate_id, ULID)


def test_scenario_uses_custom_aggregate_id():
    custom_id = ULID()
    scenario = AggregateScenario(BankAccount, aggregate_id=custom_id)
    assert scenario.aggregate_id == custom_id


def test_scenario_passes_id_to_aggregate():
    custom_id = ULID()
    scenario = AggregateScenario(BankAccount, aggregate_id=custom_id)
    assert scenario.aggregate.id == custom_id
