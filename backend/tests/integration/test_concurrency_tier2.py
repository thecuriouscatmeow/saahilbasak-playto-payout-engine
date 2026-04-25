import uuid
import threading
import pytest
from concurrent.futures import ThreadPoolExecutor, as_completed
from django.db import connection
from apps.merchants.models import Merchant, BankAccount
from apps.payouts.models import Payout, Transaction
from apps.payouts.repositories import transaction_repo, merchant_repo
from apps.payouts.services.create_payout import CreatePayoutService
from apps.payouts.domain.errors import InsufficientBalance
from apps.payouts.domain.enums import TxnType


@pytest.fixture
def merchant(db):
    return Merchant.objects.create(name="Concurrency Tier2 Merchant")


@pytest.fixture
def bank_account(merchant):
    return BankAccount.objects.create(
        merchant=merchant, ifsc="HDFC0001234", account_number="50100123456789", label="Primary"
    )


@pytest.mark.django_db(transaction=True)
def test_concurrency_tier2(merchant, bank_account):
    """₹300 merchant, 10 simultaneous ₹60 requests → exactly 5 succeed, 5 reject."""
    transaction_repo.insert_credit(str(merchant.id), 30_000)  # ₹300

    barrier = threading.Barrier(10)
    merchant_id = str(merchant.id)
    account_id = str(bank_account.id)

    def run_request():
        connection.close()
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

    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = [pool.submit(run_request) for _ in range(10)]
        results = [f.result() for f in as_completed(futures)]

    successes = results.count(201)
    failures = results.count(422)

    assert successes == 5, f"Expected 5 successes, got {successes}"
    assert failures == 5, f"Expected 5 failures, got {failures}"
    assert Payout.objects.count() == 5

    hold_total = sum(
        Transaction.objects.filter(type=TxnType.HOLD).values_list("amount_paise", flat=True)
    )
    assert hold_total == 30_000, f"Hold total should be ₹300 (30000 paise), got {hold_total}"

    balance = merchant_repo.get_balance_breakdown(merchant_id)
    assert balance.available_paise == 0
    assert balance.held_paise == 30_000
