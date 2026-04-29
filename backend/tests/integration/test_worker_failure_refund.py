import pytest
from unittest.mock import patch, MagicMock
from rest_framework.test import APIRequestFactory
from apps.merchants.models import Merchant, BankAccount
from apps.payouts.models import Transaction
from apps.payouts.repositories import transaction_repo, merchant_repo
from apps.payouts.domain.enums import PayoutStatus, TxnType
from apps.payouts.services.process_payout import ProcessPayoutService
from apps.payouts.repositories.payout_repo import create_with_hold
from apps.payouts.api.webhook import BankCallbackView


@pytest.fixture
def merchant(db):
    return Merchant.objects.create(name="Worker Failure Merchant")


@pytest.fixture
def bank_account(merchant):
    return BankAccount.objects.create(
        merchant=merchant, ifsc="HDFC0001234", account_number="50100123456789", label="Primary"
    )


@pytest.fixture
def pending_payout(merchant, bank_account):
    transaction_repo.insert_credit(str(merchant.id), 50_000)
    return create_with_hold(merchant, bank_account, 20_000)


def test_failure_atomically_releases(pending_payout, merchant):
    with patch("httpx.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200)
        svc = ProcessPayoutService(str(pending_payout.id))
        result = svc.execute()

    assert result == "processing"
    pending_payout.refresh_from_db()
    assert pending_payout.status == PayoutStatus.PROCESSING

    # Simulate webhook callback driving failure + release
    factory = APIRequestFactory()
    request = factory.post(
        "/", {"payout_id": str(pending_payout.id), "outcome": "failure"}, format="json"
    )
    response = BankCallbackView.as_view()(request)
    assert response.status_code == 200

    pending_payout.refresh_from_db()
    assert pending_payout.status == PayoutStatus.FAILED
    assert Transaction.objects.filter(type=TxnType.RELEASE).count() == 1
    balance = merchant_repo.get_balance_breakdown(str(merchant.id))
    # credit=50k, hold=20k, release=20k → available = 50k - 20k + 20k - 0 = 50k
    assert balance.available_paise == 50_000
    assert balance.held_paise == 0
