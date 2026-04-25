from django.db import transaction as db_transaction
from django.utils import timezone
from apps.payouts.models import Payout
from apps.payouts.domain.enums import PayoutStatus
from apps.payouts.repositories import payout_repo, transaction_repo
from apps.payouts.services.process_payout import simulate_bank_settlement

MAX_ATTEMPTS = 3


class RetryStalePayoutsService:
    def __init__(self, threshold_seconds: int = 30, settlement_seed: float | None = None):
        self.threshold_seconds = threshold_seconds
        self.settlement_seed = settlement_seed

    def execute(self) -> int:
        processed = 0
        with db_transaction.atomic():
            rows = payout_repo.claim_stale_with_skip_locked(self.threshold_seconds)
            for payout_id, attempts in rows:
                payout_id = str(payout_id)
                self._handle_stale(payout_id, attempts)
                processed += 1
        return processed

    def _handle_stale(self, payout_id: str, attempts: int) -> None:
        if attempts >= MAX_ATTEMPTS:
            payout = Payout.objects.get(id=payout_id)
            payout_repo.transition(
                payout_id,
                frm=PayoutStatus.PROCESSING,
                to=PayoutStatus.FAILED,
                on_apply=lambda: transaction_repo.insert_release(payout, payout.amount_paise),
                reason="max_attempts_exceeded",
            )
            return

        # Inline retry: bump attempt counter + last_attempted_at, then simulate
        from django.db.models import F
        Payout.objects.filter(id=payout_id).update(
            attempts=F("attempts") + 1,
            last_attempted_at=timezone.now(),
        )
        payout = Payout.objects.get(id=payout_id)
        outcome = simulate_bank_settlement(self.settlement_seed)

        if outcome == "success":
            payout_repo.transition(
                payout_id,
                frm=PayoutStatus.PROCESSING,
                to=PayoutStatus.COMPLETED,
                on_apply=lambda: transaction_repo.insert_debit(payout, payout.amount_paise),
                reason="bank_settled_retry",
            )
        elif outcome == "fail":
            payout_repo.transition(
                payout_id,
                frm=PayoutStatus.PROCESSING,
                to=PayoutStatus.FAILED,
                on_apply=lambda: transaction_repo.insert_release(payout, payout.amount_paise),
                reason="bank_failed_retry",
            )
        # outcome == "hang" → leave in processing for next sweep cycle
