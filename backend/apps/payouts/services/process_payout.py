import random
from django.db import transaction as db_transaction
from apps.payouts.models import Payout
from apps.payouts.domain.enums import PayoutStatus
from apps.payouts.domain.errors import InvalidStateTransition
from apps.payouts.repositories import payout_repo, transaction_repo


def simulate_bank_settlement(seed: float | None = None) -> str:
    """Returns 'success', 'fail', or 'hang'. Seed overrides random for tests."""
    r = seed if seed is not None else random.random()
    if r < 0.70:
        return "success"
    if r < 0.90:
        return "fail"
    return "hang"


class ProcessPayoutService:
    def __init__(self, payout_id: str, settlement_seed: float | None = None):
        self.payout_id = payout_id
        self.settlement_seed = settlement_seed

    def execute(self) -> str:
        try:
            payout = Payout.objects.get(id=self.payout_id)
        except Payout.DoesNotExist:
            return "not_found"

        if payout.status != PayoutStatus.PENDING:
            return "already_handled"

        try:
            with db_transaction.atomic():
                payout_repo.transition(
                    self.payout_id,
                    frm=PayoutStatus.PENDING,
                    to=PayoutStatus.PROCESSING,
                    increment_attempt=True,
                )
        except InvalidStateTransition:
            return "raced"

        payout.refresh_from_db()
        outcome = simulate_bank_settlement(self.settlement_seed)

        if outcome == "hang":
            return "hung"

        if outcome == "success":
            with db_transaction.atomic():
                payout_repo.transition(
                    self.payout_id,
                    frm=PayoutStatus.PROCESSING,
                    to=PayoutStatus.COMPLETED,
                    on_apply=lambda: transaction_repo.insert_debit(payout, payout.amount_paise),
                    reason="bank_settled",
                )
            return "completed"

        # outcome == "fail"
        with db_transaction.atomic():
            payout_repo.transition(
                self.payout_id,
                frm=PayoutStatus.PROCESSING,
                to=PayoutStatus.FAILED,
                on_apply=lambda: transaction_repo.insert_release(payout, payout.amount_paise),
                reason="bank_failed",
            )
        return "failed"
