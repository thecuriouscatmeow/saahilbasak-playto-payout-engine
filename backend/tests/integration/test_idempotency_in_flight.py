import uuid
import threading
import pytest
from apps.merchants.models import Merchant, BankAccount
from apps.payouts.repositories import transaction_repo
from apps.payouts.services.create_payout import CreatePayoutService
from apps.payouts.domain.enums import IdempotencyState
from apps.payouts.models import IdempotencyRecord


@pytest.fixture
def merchant(db):
    return Merchant.objects.create(name="InFlight Test Merchant")


@pytest.fixture
def bank_account(merchant):
    return BankAccount.objects.create(
        merchant=merchant, ifsc="HDFC0001234", account_number="50100123456789", label="Primary"
    )


@pytest.fixture
def funded_merchant(merchant):
    transaction_repo.insert_credit(str(merchant.id), 100_000)
    return merchant


def test_in_flight_second_request_returns_202_or_stored(funded_merchant, bank_account):
    """
    Microsecond-window path: record is IN_FLIGHT with no payout_id yet attached.
    A duplicate request must return 202 immediately (no sleep loop) because
    attach_payout() has not run yet. This tests the narrow window between
    insert_or_get_by_key() and the atomic attach_payout() call inside
    _run_critical_path().
    """
    from datetime import timedelta
    from django.utils import timezone
    from apps.payouts.repositories import idempotency_repo

    key = str(uuid.uuid4())
    body = {"amount_paise": 5_000, "bank_account_id": str(bank_account.id)}
    h = __import__("apps.payouts.domain.money", fromlist=["request_hash"]).request_hash(body)

    # Insert IN_FLIGHT record manually (simulates a concurrent first request mid-flight)
    idempotency_repo.insert_or_get_by_key(
        merchant_id=str(funded_merchant.id),
        key=key,
        request_hash=h,
        expires_at=timezone.now() + timedelta(hours=1),
    )
    # Record remains IN_FLIGHT — do not call update_with_response

    svc = CreatePayoutService(
        merchant_id=str(funded_merchant.id),
        amount_paise=5_000,
        bank_account_id=str(bank_account.id),
        idempotency_key=key,
        raw_body=body,
    )
    status, resp_body = svc.execute()

    # Should get 202 immediately — payout_id not yet attached (microsecond window)
    assert status == 202
    assert resp_body["status"] == "in_flight"
    assert "retry_after_ms" in resp_body


def test_in_flight_with_payout_attached_returns_live_state(funded_merchant, bank_account):
    """
    When a duplicate IN_FLIGHT request arrives and attach_payout() has already
    run (payout_id is set on the record), the service must return the live Payout
    state (HTTP 200) instead of sleeping or returning 202.
    """
    from datetime import timedelta
    from django.utils import timezone
    from apps.payouts.repositories import idempotency_repo, payout_repo

    key = str(uuid.uuid4())
    body = {"amount_paise": 7_500, "bank_account_id": str(bank_account.id)}
    h = __import__("apps.payouts.domain.money", fromlist=["request_hash"]).request_hash(body)

    # Insert IN_FLIGHT record manually
    record, _ = idempotency_repo.insert_or_get_by_key(
        merchant_id=str(funded_merchant.id),
        key=key,
        request_hash=h,
        expires_at=timezone.now() + timedelta(hours=1),
    )

    # Create a real Payout and attach it to the idempotency record
    # (simulates attach_payout() having run inside _run_critical_path)
    payout = payout_repo.create_with_hold(funded_merchant, bank_account, 7_500)
    idempotency_repo.attach_payout(str(record.id), str(payout.id))

    svc = CreatePayoutService(
        merchant_id=str(funded_merchant.id),
        amount_paise=7_500,
        bank_account_id=str(bank_account.id),
        idempotency_key=key,
        raw_body=body,
    )
    status, resp_body = svc.execute()

    assert status == 200
    assert resp_body["id"] == str(payout.id)
    assert resp_body["status"] == payout.status
    assert resp_body["amount_paise"] == 7_500
