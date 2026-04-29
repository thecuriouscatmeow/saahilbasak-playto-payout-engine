import httpx
from django.conf import settings
from django.db import transaction as db_transaction
from django.db.models import F
from django.utils import timezone
from apps.payouts.models import Payout
from apps.payouts.domain.enums import PayoutStatus
from apps.payouts.repositories import payout_repo, transaction_repo
import structlog

log = structlog.get_logger()

MAX_ATTEMPTS = 3


class RetryStalePayoutsService:
    def __init__(self, threshold_seconds: int = 30):
        self.threshold_seconds = threshold_seconds

    def execute(self) -> int:
        to_retry = []  # (payout_id, amount_paise) for HTTP calls after transaction
        processed = 0

        with db_transaction.atomic():
            rows = payout_repo.claim_stale_with_skip_locked(self.threshold_seconds)
            for payout_id, attempts in rows:
                payout_id = str(payout_id)
                payout_to_retry = self._handle_stale_db(payout_id, attempts)
                if payout_to_retry:
                    to_retry.append(payout_to_retry)
                processed += 1

        # Fire HTTP calls outside the transaction to avoid holding DB locks during network I/O
        for payout_id, amount_paise in to_retry:
            self._fire_retry_http(payout_id, amount_paise)

        return processed

    def _handle_stale_db(self, payout_id: str, attempts: int):
        """Handle DB side of stale payout. Returns (payout_id, amount_paise) if HTTP retry needed."""
        log.info("payout.retry_scheduled", payout_id=payout_id, attempts=attempts)
        if attempts >= MAX_ATTEMPTS:
            payout = Payout.objects.get(id=payout_id)
            payout_repo.transition(
                payout_id,
                frm=PayoutStatus.PROCESSING,
                to=PayoutStatus.FAILED,
                on_apply=lambda: transaction_repo.insert_release(payout, payout.amount_paise),
                reason="max_attempts_exceeded",
            )
            log.warning("payout.max_attempts_exceeded", payout_id=payout_id)
            return None

        Payout.objects.filter(id=payout_id).update(
            attempts=F("attempts") + 1,
            last_attempted_at=timezone.now(),
        )
        payout = Payout.objects.get(id=payout_id)
        return (payout_id, payout.amount_paise)

    def _fire_retry_http(self, payout_id: str, amount_paise: int) -> None:
        try:
            httpx.post(
                settings.BANK_SIMULATOR_URL + "/settle",
                json={
                    "payout_id": payout_id,
                    "amount_paise": amount_paise,
                    "callback_url": settings.ENGINE_WEBHOOK_URL,
                },
                timeout=5.0,
            )
        except Exception:
            pass
