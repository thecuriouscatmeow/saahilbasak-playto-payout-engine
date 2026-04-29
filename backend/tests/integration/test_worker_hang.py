import pytest
from unittest.mock import patch, MagicMock
from apps.merchants.models import Merchant, BankAccount
from apps.payouts.repositories import transaction_repo
from apps.payouts.domain.enums import PayoutStatus
from apps.payouts.services.process_payout import ProcessPayoutService
from apps.payouts.repositories.payout_repo import create_with_hold


@pytest.fixture
def merchant(db):
    return Merchant.objects.create(name="Worker Hang Merchant")


@pytest.fixture
def bank_account(merchant):
    return BankAccount.objects.create(
        merchant=merchant, ifsc="HDFC0001234", account_number="50100123456789", label="Primary"
    )


@pytest.fixture
def pending_payout(merchant, bank_account):
    transaction_repo.insert_credit(str(merchant.id), 50_000)
    return create_with_hold(merchant, bank_account, 20_000)


def test_hang_leaves_processing(pending_payout):
    # Simulate a "pending" outcome: bank simulator fires HTTP but sends no callback
    with patch("httpx.post", return_value=MagicMock(status_code=200)):
        result = ProcessPayoutService(str(pending_payout.id)).execute()

    assert result == "processing"
    pending_payout.refresh_from_db()
    assert pending_payout.status == PayoutStatus.PROCESSING
    assert pending_payout.attempts == 1
