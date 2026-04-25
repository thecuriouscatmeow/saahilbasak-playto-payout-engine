import pytest
from datetime import timedelta
from django.utils import timezone
from apps.merchants.models import Merchant, BankAccount
from apps.payouts.models import Payout, Transaction
from apps.payouts.repositories import transaction_repo, merchant_repo
from apps.payouts.domain.enums import PayoutStatus, TxnType
from apps.payouts.services.process_payout import ProcessPayoutService
from apps.payouts.services.retry_stale import RetryStalePayoutsService
from apps.payouts.repositories.payout_repo import create_with_hold


def backdate_payout(payout, seconds=60):
    Payout.objects.filter(id=payout.id).update(
        last_attempted_at=timezone.now() - timedelta(seconds=seconds)
    )
    payout.refresh_from_db()


@pytest.fixture
def merchant(db):
    return Merchant.objects.create(name="Hang Retry Max Merchant")


@pytest.fixture
def bank_account(merchant):
    return BankAccount.objects.create(
        merchant=merchant, ifsc="HDFC0001234", account_number="50100123456789", label="Primary"
    )


@pytest.fixture
def funded_merchant(merchant):
    transaction_repo.insert_credit(str(merchant.id), 50_000)
    return merchant


def test_hang_retry_to_max_then_fail(funded_merchant, bank_account):
    payout = create_with_hold(funded_merchant, bank_account, 20_000)

    # Attempt 1: worker picks up, hang → status=processing, attempts=1
    result = ProcessPayoutService(str(payout.id), settlement_seed=0.95).execute()
    assert result == "hung"
    payout.refresh_from_db()
    assert payout.status == PayoutStatus.PROCESSING
    assert payout.attempts == 1

    # Sweeper attempt 2: still hang → attempts=2
    backdate_payout(payout)
    swept = RetryStalePayoutsService(threshold_seconds=30, settlement_seed=0.95).execute()
    assert swept == 1
    payout.refresh_from_db()
    assert payout.status == PayoutStatus.PROCESSING
    assert payout.attempts == 2

    # Sweeper attempt 3: still hang → attempts=3
    backdate_payout(payout)
    swept = RetryStalePayoutsService(threshold_seconds=30, settlement_seed=0.95).execute()
    assert swept == 1
    payout.refresh_from_db()
    assert payout.status == PayoutStatus.PROCESSING
    assert payout.attempts == 3

    # Sweeper attempt 4: attempts >= MAX_ATTEMPTS → forced FAILED + release
    backdate_payout(payout)
    swept = RetryStalePayoutsService(threshold_seconds=30, settlement_seed=0.95).execute()
    assert swept == 1
    payout.refresh_from_db()
    assert payout.status == PayoutStatus.FAILED

    # Ledger invariant: release restores balance
    assert Transaction.objects.filter(type=TxnType.RELEASE).count() == 1
    balance = merchant_repo.get_balance_breakdown(str(funded_merchant.id))
    assert balance.available_paise == 50_000  # fully restored
    assert balance.held_paise == 0
