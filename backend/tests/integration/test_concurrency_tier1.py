import uuid
import threading
import pytest
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor, as_completed
from django.db import connection
from apps.merchants.models import Merchant, BankAccount
from apps.payouts.models import Payout
from apps.payouts.repositories import transaction_repo, merchant_repo
from apps.payouts.services.create_payout import CreatePayoutService
from apps.payouts.domain.errors import InsufficientBalance


@pytest.fixture
def merchant(db):
    return Merchant.objects.create(name="Concurrency Tier1 Merchant")


@pytest.fixture
def bank_account(merchant):
    return BankAccount.objects.create(
        merchant=merchant, ifsc="HDFC0001234", account_number="50100123456789", label="Primary"
    )


@pytest.mark.django_db(transaction=True)
@patch("apps.payouts.services.process_payout.ProcessPayoutService.execute", return_value="pending")
def test_concurrency_tier1(mock_execute, merchant, bank_account):
    """₹100 merchant, 2 simultaneous ₹60 requests → exactly 1 success, 1 reject."""
    transaction_repo.insert_credit(str(merchant.id), 10_000)  # ₹100

    barrier = threading.Barrier(2)
    results = []
    merchant_id = str(merchant.id)
    account_id = str(bank_account.id)

    def run_request():
        connection.close()  # force fresh connection per thread
        barrier.wait()
        key = str(uuid.uuid4())
        body = {"amount_paise": 6_000, "bank_account_id": account_id}
        svc = CreatePayoutService(
            merchant_id=merchant_id,
            amount_paise=6_000,
            bank_account_id=account_id,
            idempotency_key=key,
            raw_body=body,
        )
        try:
            status, _ = svc.execute()
            return status
        except InsufficientBalance:
            return 422
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run_request) for _ in range(2)]
        results = [f.result() for f in as_completed(futures)]

    assert sorted(results) == [201, 422], f"Expected [201, 422], got {sorted(results)}"
    assert Payout.objects.count() == 1

    balance = merchant_repo.get_balance_breakdown(merchant_id)
    assert balance.available_paise >= 0, "Balance must never go negative"
    # Winner took ₹60, so available = 100 - 60 = 40
    assert balance.available_paise == 4_000
