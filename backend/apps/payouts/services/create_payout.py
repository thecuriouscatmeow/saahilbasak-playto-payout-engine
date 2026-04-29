from datetime import timedelta
from django.db import transaction as db_transaction
from django.utils import timezone
from apps.merchants.models import BankAccount
from apps.payouts.repositories import merchant_repo, payout_repo, idempotency_repo
from apps.payouts.domain.enums import IdempotencyState
from apps.payouts.domain.errors import (
    InsufficientBalance,
    BankAccountNotFound,
    IdempotencyPayloadMismatch,
)
from apps.payouts.domain.money import request_hash as compute_hash
import structlog
log = structlog.get_logger()


class CreatePayoutService:
    IDEMPOTENCY_TTL_HOURS = 24

    def __init__(
        self,
        merchant_id: str,
        amount_paise: int,
        bank_account_id: str,
        idempotency_key: str,
        raw_body: dict,
    ):
        self.merchant_id = merchant_id
        self.amount_paise = amount_paise
        self.bank_account_id = bank_account_id
        self.idempotency_key = idempotency_key
        self.request_hash = compute_hash(raw_body)

    def execute(self) -> tuple[int, dict]:
        expires_at = timezone.now() + timedelta(hours=self.IDEMPOTENCY_TTL_HOURS)
        record, created = idempotency_repo.insert_or_get_by_key(
            merchant_id=self.merchant_id,
            key=self.idempotency_key,
            request_hash=self.request_hash,
            expires_at=expires_at,
        )

        if not created:
            return self._handle_existing_record(record)

        try:
            status_code, body = self._run_critical_path(record_id=str(record.id))
        except InsufficientBalance:
            idempotency_repo.update_with_response(
                record_id=str(record.id),
                payout_id=None,
                response_status_code=422,
                response_body={"error": "insufficient_balance"},
            )
            raise

        idempotency_repo.update_with_response(
            record_id=str(record.id),
            payout_id=body["id"],
            response_status_code=status_code,
            response_body=body,
        )
        log.info("payout.created", payout_id=body["id"], merchant_id=self.merchant_id, amount_paise=self.amount_paise)
        return status_code, body

    def _run_critical_path(self, record_id: str) -> tuple[int, dict]:
        with db_transaction.atomic():
            merchant = merchant_repo.lock_for_update(self.merchant_id)

            try:
                bank_account = BankAccount.objects.get(
                    id=self.bank_account_id, merchant=merchant, is_active=True
                )
            except BankAccount.DoesNotExist:
                raise BankAccountNotFound(account_id=self.bank_account_id)

            balance = merchant_repo.get_balance_breakdown(self.merchant_id)
            if balance.available_paise < self.amount_paise:
                raise InsufficientBalance(
                    merchant_id=self.merchant_id,
                    requested_paise=self.amount_paise,
                    available_paise=balance.available_paise,
                )

            payout = payout_repo.create_with_hold(merchant, bank_account, self.amount_paise)
            idempotency_repo.attach_payout(record_id, str(payout.id))

        from apps.payouts.tasks.payout_tasks import process_payout
        from observability.correlation import get_correlation_id
        process_payout.apply_async(
            args=[str(payout.id)],
            kwargs={"correlation_id": get_correlation_id()},
        )

        body = {
            "id": str(payout.id),
            "merchant_id": str(payout.merchant_id),
            "bank_account_id": str(payout.bank_account_id),
            "amount_paise": payout.amount_paise,
            "status": payout.status,
        }
        return 201, body

    def _handle_existing_record(self, record) -> tuple[int, dict]:
        if record.request_hash != self.request_hash:
            log.warning("idempotency.payload_mismatch", idempotency_key=self.idempotency_key, merchant_id=self.merchant_id)
            raise IdempotencyPayloadMismatch(idempotency_key=self.idempotency_key)

        if record.state == IdempotencyState.COMPLETED:
            stored = dict(record.response_body)
            status = stored.pop("_status", 201)
            log.info("idempotency.replayed", idempotency_key=self.idempotency_key, merchant_id=self.merchant_id)
            return status, stored

        # Refresh to get latest payout_id (may have been set by now)
        record.refresh_from_db()
        if record.payout_id:
            from apps.payouts.models import Payout
            payout = Payout.objects.get(id=record.payout_id)
            return 200, {
                "id": str(payout.id),
                "merchant_id": str(payout.merchant_id),
                "bank_account_id": str(payout.bank_account_id),
                "amount_paise": payout.amount_paise,
                "status": payout.status,
            }

        # payout_id not yet set (microsecond window between record insert and attach_payout)
        log.info("idempotency.in_flight", idempotency_key=self.idempotency_key, merchant_id=self.merchant_id)
        return 202, {
            "status": "in_flight",
            "idempotency_key": self.idempotency_key,
            "retry_after_ms": 500,
        }
