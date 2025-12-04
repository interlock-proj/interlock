"""Event processors and sagas for testing."""

from decimal import Decimal
from pydantic import BaseModel

from interlock.application.events import EventProcessor, Saga
from interlock.application.events.processing import saga_step, SagaStateStore
from interlock.routing import handles_event

from .aggregates.bank_account import (
    AccountOpened,
    MoneyDeposited,
    MoneyWithdrawn,
)


# Event Processor for testing
class AccountStatisticsProcessor(EventProcessor):
    """Tracks account statistics from banking events."""

    def __init__(self):
        super().__init__()
        self.total_accounts_opened: int = 0
        self.total_deposits: Decimal = Decimal("0.00")
        self.total_withdrawals: Decimal = Decimal("0.00")
        self.deposit_count: int = 0
        self.withdrawal_count: int = 0

    @handles_event
    async def on_account_opened(self, event: AccountOpened) -> None:
        self.total_accounts_opened += 1

    @handles_event
    async def on_money_deposited(self, event: MoneyDeposited) -> None:
        self.total_deposits += event.amount
        self.deposit_count += 1

    @handles_event
    async def on_money_withdrawn(self, event: MoneyWithdrawn) -> None:
        self.total_withdrawals += event.amount
        self.withdrawal_count += 1


# Saga State Models
class TransferSagaState(BaseModel):
    """State for money transfer saga."""

    transfer_id: str
    from_account: str
    to_account: str
    amount: Decimal
    source_withdrawn: bool = False
    destination_deposited: bool = False
    completed: bool = False


class TransferInitiated(BaseModel):
    """Event to initiate a transfer."""

    saga_id: str
    from_account: str
    to_account: str
    amount: Decimal


class TransferCompleted(BaseModel):
    """Event when transfer completes."""

    saga_id: str


class TransferFailed(BaseModel):
    """Event when transfer fails."""

    saga_id: str
    reason: str


# Money Transfer Saga for testing
class MoneyTransferSaga(Saga[TransferSagaState]):
    """Coordinates money transfer between accounts."""

    def __init__(self, state_store: SagaStateStore):
        super().__init__(state_store)
        self.transfer_completed_count: int = 0
        self.transfer_failed_count: int = 0

    @saga_step
    async def on_transfer_initiated(
        self, event: TransferInitiated
    ) -> TransferSagaState:
        return TransferSagaState(
            transfer_id=event.saga_id,
            from_account=event.from_account,
            to_account=event.to_account,
            amount=event.amount,
        )

    @saga_step
    async def on_money_withdrawn(
        self, event: MoneyWithdrawn, state: TransferSagaState
    ) -> TransferSagaState:
        # This would typically be triggered by a WithdrawalCompleted event
        # with saga_id, but we're reusing the bank events for simplicity
        state.source_withdrawn = True
        return state

    @saga_step
    async def on_transfer_completed(
        self, event: TransferCompleted, state: TransferSagaState
    ) -> TransferSagaState:
        state.completed = True
        self.transfer_completed_count += 1
        return state

    @saga_step
    async def on_transfer_failed(
        self, event: TransferFailed, state: TransferSagaState
    ) -> None:
        self.transfer_failed_count += 1
        return None  # Delete state
