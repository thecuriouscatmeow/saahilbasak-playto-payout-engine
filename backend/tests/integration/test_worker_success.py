import pytest
from apps.merchants.models import Merchant, BankAccount
from apps.payouts.models import Payout, Transaction
from apps.payouts.repositories import transaction_repo, merchant_repo
from apps.payouts.domain.enums import PayoutStatus, TxnType
from apps.payouts.services.process_payout import ProcessPayoutService


@pytest.fixture
def merchant(db):
    return Merchant.objects.create(name="Worker Success Merchant")


@pytest.fixture
def bank_account(merchant):
    return BankAccount.objects.create(
        merchant=merchant, ifsc="HDFC0001234", account_number="50100123456789", label="Primary"
    )


@pytest.fixture
def pending_payout(merchant, bank_account):
    transaction_repo.insert_credit(str(merchant.id), 50_000)
    from apps.payouts.repositories.payout_repo import create_with_hold
    return create_with_hold(merchant, bank_account, 20_000)


def test_success_path(pending_payout, merchant):
    svc = ProcessPayoutService(str(pending_payout.id), settlement_seed=0.5)  # < 0.70 → success
    result = svc.execute()

    assert result == "completed"
    pending_payout.refresh_from_db()
    assert pending_payout.status == PayoutStatus.COMPLETED

    assert Transaction.objects.filter(type=TxnType.DEBIT).count() == 1
    balance = merchant_repo.get_balance_breakdown(str(merchant.id))
    # credit=50k, hold=20k, debit=20k → available = 50k - 20k + 0 - 20k = 10k
    assert balance.available_paise == 10_000
    assert balance.held_paise == 0


def test_already_handled_is_noop(pending_payout):
    ProcessPayoutService(str(pending_payout.id), settlement_seed=0.5).execute()
    result = ProcessPayoutService(str(pending_payout.id), settlement_seed=0.5).execute()
    assert result == "already_handled"
    assert Payout.objects.count() == 1
