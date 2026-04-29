import httpx
from django.conf import settings
from django.db import transaction as db_transaction
from apps.payouts.models import Payout
from apps.payouts.domain.enums import PayoutStatus
from apps.payouts.domain.errors import InvalidStateTransition
from apps.payouts.repositories import payout_repo, transaction_repo


class ProcessPayoutService:
    def __init__(self, payout_id: str):
        self.payout_id = payout_id

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
        try:
            httpx.post(
                settings.BANK_SIMULATOR_URL + "/settle",
                json={
                    "payout_id": self.payout_id,
                    "amount_paise": payout.amount_paise,
                    "callback_url": settings.ENGINE_WEBHOOK_URL,
                },
                timeout=5.0,
            )
        except Exception:
            pass  # sweeper will retry on timeout/network error
        return "processing"
