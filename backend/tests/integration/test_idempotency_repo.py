import pytest
from datetime import timedelta
from django.utils import timezone
from apps.merchants.models import Merchant
from apps.payouts.repositories import idempotency_repo


@pytest.fixture
def merchant(db):
    return Merchant.objects.create(name="Idempotency Test Merchant")


def make_key():
    import uuid
    return str(uuid.uuid4())


def future():
    return timezone.now() + timedelta(hours=24)


def past():
    return timezone.now() - timedelta(seconds=1)


def test_first_insert_creates(merchant):
    record, created = idempotency_repo.insert_or_get_by_key(
        merchant_id=str(merchant.id),
        key=make_key(),
        request_hash="a" * 64,
        expires_at=future(),
    )
    assert created is True
    assert record.idempotency_key is not None


def test_second_insert_returns_existing(merchant):
    key = make_key()
    r1, c1 = idempotency_repo.insert_or_get_by_key(str(merchant.id), key, "a" * 64, future())
    r2, c2 = idempotency_repo.insert_or_get_by_key(str(merchant.id), key, "b" * 64, future())
    assert c1 is True
    assert c2 is False
    assert str(r1.id) == str(r2.id)


def test_expired_record_treated_as_absent(merchant):
    key = make_key()
    # Insert with past expiry
    r1, c1 = idempotency_repo.insert_or_get_by_key(str(merchant.id), key, "a" * 64, past())
    assert c1 is True
    # Second insert should see it as absent and create fresh
    r2, c2 = idempotency_repo.insert_or_get_by_key(str(merchant.id), key, "b" * 64, future())
    assert c2 is True
    assert str(r1.id) != str(r2.id)


def test_update_with_response(merchant):
    key = make_key()
    record, _ = idempotency_repo.insert_or_get_by_key(str(merchant.id), key, "a" * 64, future())
    idempotency_repo.update_with_response(
        record_id=str(record.id),
        payout_id=None,
        response_status_code=201,
        response_body={"id": "some-payout-id"},
    )
    from apps.payouts.models import IdempotencyRecord
    from apps.payouts.domain.enums import IdempotencyState
    updated = IdempotencyRecord.objects.get(id=record.id)
    assert updated.state == IdempotencyState.COMPLETED
    assert updated.response_body["id"] == "some-payout-id"
    assert updated.response_body["_status"] == 201
