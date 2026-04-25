import pytest
from datetime import timedelta
from django.utils import timezone
from apps.merchants.models import Merchant
from apps.payouts.models import IdempotencyRecord
from apps.payouts.domain.enums import IdempotencyState
from apps.payouts.tasks.expire_idempotency import expire_idempotency


@pytest.fixture
def merchant(db):
    return Merchant.objects.create(name="Expiry Test Merchant")


def test_expire_idempotency_deletes_expired(merchant):
    IdempotencyRecord.objects.create(
        merchant=merchant,
        idempotency_key="old-key",
        request_hash="a" * 64,
        state=IdempotencyState.COMPLETED,
        expires_at=timezone.now() - timedelta(hours=1),
    )
    IdempotencyRecord.objects.create(
        merchant=merchant,
        idempotency_key="new-key",
        request_hash="b" * 64,
        state=IdempotencyState.IN_FLIGHT,
        expires_at=timezone.now() + timedelta(hours=24),
    )

    result = expire_idempotency()

    assert result["purged"] == 1
    assert IdempotencyRecord.objects.filter(idempotency_key="old-key").count() == 0
    assert IdempotencyRecord.objects.filter(idempotency_key="new-key").count() == 1
