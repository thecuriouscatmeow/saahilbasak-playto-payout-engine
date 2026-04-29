from datetime import datetime
from django.db import transaction as db_transaction
from django.utils import timezone
from apps.payouts.models import IdempotencyRecord
from apps.payouts.domain.enums import IdempotencyState


def insert_or_get_by_key(
    merchant_id: str,
    key: str,
    request_hash: str,
    expires_at: datetime,
) -> tuple[IdempotencyRecord, bool]:
    with db_transaction.atomic():
        # Delete expired record for this key so it's treated as absent
        IdempotencyRecord.objects.filter(
            merchant_id=merchant_id,
            idempotency_key=key,
            expires_at__lt=timezone.now(),
        ).delete()

        record, created = IdempotencyRecord.objects.get_or_create(
            merchant_id=merchant_id,
            idempotency_key=key,
            defaults={
                "request_hash": request_hash,
                "state": IdempotencyState.IN_FLIGHT,
                "expires_at": expires_at,
            },
        )
    return record, created


def update_with_response(
    record_id: str,
    *,
    payout_id: str | None,
    response_status_code: int,
    response_body: dict,
) -> None:
    stored_body = {"_status": response_status_code, **response_body}
    IdempotencyRecord.objects.filter(id=record_id).update(
        payout_id=payout_id,
        state=IdempotencyState.COMPLETED,
        response_body=stored_body,
    )


def attach_payout(record_id: str, payout_id: str) -> None:
    """Set payout FK on IN_FLIGHT record so duplicates can return live state."""
    IdempotencyRecord.objects.filter(id=record_id).update(payout_id=payout_id)


def purge_expired() -> int:
    deleted, _ = IdempotencyRecord.objects.filter(expires_at__lt=timezone.now()).delete()
    return deleted
