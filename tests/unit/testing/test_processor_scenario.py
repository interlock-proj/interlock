"""Tests for ProcessorScenario."""

from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from interlock.application.events.processing import EventProcessor
from interlock.routing import handles_event
from interlock.testing import ProcessorScenario
from tests.fixtures.test_app import AccountStatisticsProcessor
from tests.fixtures.test_app.aggregates.bank_account import (
    AccountOpened,
    MoneyDeposited,
    MoneyWithdrawn,
)

if TYPE_CHECKING:
    from pydantic import BaseModel


class FailingProcessor(EventProcessor):
    """Processor that raises errors for testing error handling."""

    def __init__(self):
        super().__init__()
        self.processed_events: list[BaseModel] = []

    @handles_event
    async def on_account_opened(self, event: AccountOpened) -> None:
        raise ValueError("Intentional failure for testing")

    @handles_event
    async def on_money_deposited(self, event: MoneyDeposited) -> None:
        self.processed_events.append(event)


@pytest.mark.asyncio
async def test_processor_handles_single_event():
    """Test that processor handles a single event correctly."""
    scenario = ProcessorScenario(AccountStatisticsProcessor)

    scenario.given(AccountOpened(owner="Alice")).should_have_state(
        lambda p: p.total_accounts_opened == 1
    )

    await scenario.execute_scenario()


@pytest.mark.asyncio
async def test_processor_handles_multiple_events():
    """Test that processor handles multiple events correctly."""
    scenario = ProcessorScenario(AccountStatisticsProcessor)

    scenario.given(
        AccountOpened(owner="Alice"),
        MoneyDeposited(amount=Decimal("100.00")),
        MoneyDeposited(amount=Decimal("50.00")),
    ).should_have_state(lambda p: p.total_accounts_opened == 1 and p.deposit_count == 2)

    await scenario.execute_scenario()


@pytest.mark.asyncio
async def test_processor_tracks_deposits():
    """Test that processor correctly tracks deposit amounts."""
    scenario = ProcessorScenario(AccountStatisticsProcessor)

    scenario.given(
        MoneyDeposited(amount=Decimal("100.00")),
        MoneyDeposited(amount=Decimal("200.00")),
        MoneyDeposited(amount=Decimal("50.00")),
    ).should_have_state(lambda p: p.total_deposits == Decimal("350.00"))

    await scenario.execute_scenario()


@pytest.mark.asyncio
async def test_processor_tracks_withdrawals():
    """Test that processor correctly tracks withdrawal amounts."""
    scenario = ProcessorScenario(AccountStatisticsProcessor)

    scenario.given(
        MoneyWithdrawn(amount=Decimal("100.00")),
        MoneyWithdrawn(amount=Decimal("50.00")),
    ).should_have_state(
        lambda p: p.total_withdrawals == Decimal("150.00") and p.withdrawal_count == 2
    )

    await scenario.execute_scenario()


@pytest.mark.asyncio
async def test_processor_tracks_mixed_events():
    """Test that processor correctly tracks all event types."""
    scenario = ProcessorScenario(AccountStatisticsProcessor)

    scenario.given(
        AccountOpened(owner="Bob"),
        AccountOpened(owner="Charlie"),
        MoneyDeposited(amount=Decimal("100.00")),
        MoneyWithdrawn(amount=Decimal("25.00")),
        MoneyDeposited(amount=Decimal("50.00")),
    ).should_have_state(
        lambda p: (
            p.total_accounts_opened == 2
            and p.total_deposits == Decimal("150.00")
            and p.total_withdrawals == Decimal("25.00")
            and p.deposit_count == 2
            and p.withdrawal_count == 1
        )
    )

    await scenario.execute_scenario()


@pytest.mark.asyncio
async def test_processor_given_no_events():
    """Test processor with no events."""
    scenario = ProcessorScenario(AccountStatisticsProcessor)

    scenario.given_no_events().should_have_state(lambda p: p.total_accounts_opened == 0)

    await scenario.execute_scenario()


@pytest.mark.asyncio
async def test_processor_handles_errors():
    """Test that processor errors are captured."""
    scenario = ProcessorScenario(FailingProcessor)

    scenario.given(AccountOpened(owner="Dave")).should_raise(ValueError)

    await scenario.execute_scenario()


@pytest.mark.asyncio
async def test_processor_error_doesnt_stop_other_events():
    """Test that errors in one event don't stop processing of others."""
    scenario = ProcessorScenario(FailingProcessor)

    scenario.given(
        AccountOpened(owner="Eve"),  # This will fail
        MoneyDeposited(amount=Decimal("100.00")),  # This should still process
    ).should_raise(ValueError).should_have_state(lambda p: len(p.processed_events) == 1)

    await scenario.execute_scenario()


@pytest.mark.asyncio
async def test_processor_chainable_given():
    """Test that given() is chainable."""
    scenario = ProcessorScenario(AccountStatisticsProcessor)

    scenario.given(AccountOpened(owner="Frank")).given(
        MoneyDeposited(amount=Decimal("100.00"))
    ).should_have_state(lambda p: p.total_accounts_opened == 1 and p.deposit_count == 1)

    await scenario.execute_scenario()


@pytest.mark.asyncio
async def test_processor_multiple_state_checks():
    """Test multiple state predicates."""
    scenario = ProcessorScenario(AccountStatisticsProcessor)

    scenario.given(
        MoneyDeposited(amount=Decimal("100.00")),
        MoneyWithdrawn(amount=Decimal("50.00")),
    ).should_have_state(lambda p: p.total_deposits == Decimal("100.00")).should_have_state(
        lambda p: p.total_withdrawals == Decimal("50.00")
    )

    await scenario.execute_scenario()


@pytest.mark.asyncio
async def test_processor_state_predicate_fails():
    """Test that failed state predicate raises AssertionError."""
    with pytest.raises(AssertionError, match="should match state"):
        scenario = ProcessorScenario(AccountStatisticsProcessor)

        scenario.given(MoneyDeposited(amount=Decimal("100.00"))).should_have_state(
            lambda p: p.total_deposits == Decimal("200.00")  # Wrong amount
        )

        await scenario.execute_scenario()


@pytest.mark.asyncio
async def test_processor_without_context_manager():
    """Test processor scenario without using context manager."""
    scenario = ProcessorScenario(AccountStatisticsProcessor)

    scenario.given(AccountOpened(owner="Grace")).should_have_state(
        lambda p: p.total_accounts_opened == 1
    )

    await scenario.execute_scenario()


@pytest.mark.asyncio
async def test_processor_complex_state_check():
    """Test complex state validation logic."""
    scenario = ProcessorScenario(AccountStatisticsProcessor)

    scenario.given(
        AccountOpened(owner="Henry"),
        MoneyDeposited(amount=Decimal("100.00")),
        MoneyDeposited(amount=Decimal("200.00")),
        MoneyWithdrawn(amount=Decimal("50.00")),
    ).should_have_state(
        lambda p: (
            p.total_deposits > p.total_withdrawals
            and p.deposit_count == 2
            and p.withdrawal_count == 1
            and p.total_deposits - p.total_withdrawals == Decimal("250.00")
        )
    )

    await scenario.execute_scenario()


@pytest.mark.asyncio
async def test_processor_scenario_fails_when_expected_error_missing():
    """Test that scenario fails when expected error is not raised."""
    with pytest.raises(AssertionError, match="should contain error of type"):
        scenario = ProcessorScenario(AccountStatisticsProcessor)

        scenario.given(MoneyDeposited(amount=Decimal("100.00"))).should_raise(ValueError)

        await scenario.execute_scenario()


@pytest.mark.asyncio
async def test_processor_handles_empty_event_list():
    """Test processor with explicitly cleared event list."""
    scenario = ProcessorScenario(AccountStatisticsProcessor)

    scenario.given(AccountOpened(owner="Iris")).given_no_events().should_have_state(
        lambda p: p.total_accounts_opened == 0
    )

    await scenario.execute_scenario()


@pytest.mark.asyncio
async def test_processor_state_with_decimal_precision():
    """Test that processor handles decimal precision correctly."""
    scenario = ProcessorScenario(AccountStatisticsProcessor)

    scenario.given(
        MoneyDeposited(amount=Decimal("100.01")),
        MoneyDeposited(amount=Decimal("0.99")),
    ).should_have_state(lambda p: p.total_deposits == Decimal("101.00"))

    await scenario.execute_scenario()


@pytest.mark.asyncio
async def test_processor_multiple_error_expectations():
    """Test processor with multiple error expectations."""
    scenario = ProcessorScenario(FailingProcessor)

    scenario.given(
        AccountOpened(owner="Jack"),
        AccountOpened(owner="Kate"),
    ).should_raise(ValueError)

    await scenario.execute_scenario()

    # Both events should have caused errors
    assert len(scenario.errors) == 2


@pytest.mark.asyncio
async def test_processor_verifies_zero_values():
    """Test that processor correctly handles zero values."""
    scenario = ProcessorScenario(AccountStatisticsProcessor)

    scenario.given_no_events().should_have_state(
        lambda p: (
            p.total_deposits == Decimal("0.00")
            and p.total_withdrawals == Decimal("0.00")
            and p.deposit_count == 0
            and p.withdrawal_count == 0
        )
    )

    await scenario.execute_scenario()


@pytest.mark.asyncio
async def test_processor_large_number_of_events():
    """Test processor with many events."""
    scenario = ProcessorScenario(AccountStatisticsProcessor)

    events = [MoneyDeposited(amount=Decimal("10.00")) for _ in range(100)]

    scenario.given(*events).should_have_state(
        lambda p: p.deposit_count == 100 and p.total_deposits == Decimal("1000.00")
    )

    await scenario.execute_scenario()


@pytest.mark.asyncio
async def test_processor_scenario_can_check_intermediate_state():
    """Test that we can verify processor state at any point."""
    scenario = ProcessorScenario(AccountStatisticsProcessor)

    # First batch
    scenario.given(MoneyDeposited(amount=Decimal("100.00")))

    await scenario.execute_scenario()

    # Verify first state
    assert scenario.processor.total_deposits == Decimal("100.00")


@pytest.mark.asyncio
async def test_processor_with_context_manager():
    """Test processor scenario with async context manager."""
    async with ProcessorScenario(AccountStatisticsProcessor) as scenario:
        scenario.given(
            AccountOpened(owner="Leo"), MoneyDeposited(amount=Decimal("50.00"))
        ).should_have_state(lambda p: p.total_accounts_opened == 1 and p.deposit_count == 1)
