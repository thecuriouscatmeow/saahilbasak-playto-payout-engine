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
    When a record is IN_FLIGHT (inserted but not completed), a second request
    with the same key should either get 202 (still in flight after polling) or
    the completed response if it completes during the poll window.
    We simulate IN_FLIGHT by inserting the record directly and NOT completing it.
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

    # Should get 202 (record still in_flight after poll exhaustion)
    assert status == 202
    assert resp_body["status"] == "in_flight"
    assert "retry_after_ms" in resp_body
