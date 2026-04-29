import threading
import uuid
import pytest
from datetime import timedelta
from unittest.mock import patch, MagicMock
from django.utils import timezone
from django.db import connection
from rest_framework.test import APIRequestFactory
from apps.merchants.models import Merchant, BankAccount
from apps.payouts.models import Payout, PayoutEvent, Transaction
from apps.payouts.repositories import transaction_repo, merchant_repo
from apps.payouts.domain.enums import PayoutStatus, TxnType
from apps.payouts.services.retry_stale import RetryStalePayoutsService
from apps.payouts.repositories.payout_repo import create_with_hold
from apps.payouts.api.webhook import BankCallbackView


def _fire_webhook(payout_id: str, outcome: str) -> None:
    factory = APIRequestFactory()
    request = factory.post("/", {"payout_id": payout_id, "outcome": outcome}, format="json")
    BankCallbackView.as_view()(request)


def make_stale_processing_payout(merchant, bank_account, attempts=0, seconds_ago=60):
    payout = create_with_hold(merchant, bank_account, 10_000)
    Payout.objects.filter(id=payout.id).update(
        status=PayoutStatus.PROCESSING,
        attempts=attempts,
        last_attempted_at=timezone.now() - timedelta(seconds=seconds_ago),
    )
    payout.refresh_from_db()
    return payout


@pytest.fixture
def merchant(db):
    return Merchant.objects.create(name="Sweeper Test Merchant")


@pytest.fixture
def bank_account(merchant):
    return BankAccount.objects.create(
        merchant=merchant, ifsc="HDFC0001234", account_number="50100123456789", label="Primary"
    )


@pytest.fixture
def funded_merchant(merchant):
    transaction_repo.insert_credit(str(merchant.id), 100_000)
    return merchant


def test_sweeper_fails_at_max_attempts(funded_merchant, bank_account):
    payout = make_stale_processing_payout(funded_merchant, bank_account, attempts=3)
    svc = RetryStalePayoutsService(threshold_seconds=30)
    count = svc.execute()

    assert count == 1
    payout.refresh_from_db()
    assert payout.status == PayoutStatus.FAILED

    event = PayoutEvent.objects.filter(payout=payout, to_status=PayoutStatus.FAILED).first()
    assert event is not None
    assert "max_attempts" in event.note

    assert Transaction.objects.filter(type=TxnType.RELEASE).count() == 1
    balance = merchant_repo.get_balance_breakdown(str(funded_merchant.id))
    assert balance.available_paise == 100_000  # fully restored


def test_sweeper_retries_and_fails(funded_merchant, bank_account):
    payout = make_stale_processing_payout(funded_merchant, bank_account, attempts=2)
    with patch("httpx.post", return_value=MagicMock(status_code=200)):
        RetryStalePayoutsService(threshold_seconds=30).execute()
    # Sweeper re-fired HTTP; simulate bank callback arriving with failure
    _fire_webhook(str(payout.id), "failure")

    payout.refresh_from_db()
    assert payout.status == PayoutStatus.FAILED
    assert Transaction.objects.filter(type=TxnType.RELEASE).count() == 1


def test_sweeper_retries_and_succeeds(funded_merchant, bank_account):
    payout = make_stale_processing_payout(funded_merchant, bank_account, attempts=1)
    with patch("httpx.post", return_value=MagicMock(status_code=200)):
        RetryStalePayoutsService(threshold_seconds=30).execute()
    # Sweeper re-fired HTTP; simulate bank callback arriving with success
    _fire_webhook(str(payout.id), "success")

    payout.refresh_from_db()
    assert payout.status == PayoutStatus.COMPLETED
    assert Transaction.objects.filter(type=TxnType.DEBIT).count() == 1


@pytest.mark.django_db(transaction=True)
def test_sweeper_skip_locked_no_double_claim(funded_merchant, bank_account):
    """Two concurrent sweeper invocations must not double-process the same payout."""
    payout = make_stale_processing_payout(funded_merchant, bank_account, attempts=3)
    results = []

    def run_sweeper():
        connection.close()
        svc = RetryStalePayoutsService(threshold_seconds=30)
        results.append(svc.execute())
        connection.close()

    t1 = threading.Thread(target=run_sweeper)
    t2 = threading.Thread(target=run_sweeper)
    t1.start(); t2.start()
    t1.join(); t2.join()

    # Between both sweepers, exactly 1 payout should be processed
    assert sum(results) == 1
    assert Transaction.objects.filter(type=TxnType.RELEASE).count() == 1
