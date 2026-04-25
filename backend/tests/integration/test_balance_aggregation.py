import pytest
from apps.merchants.models import Merchant, BankAccount
from apps.payouts.models import Payout, Transaction
from apps.payouts.domain.enums import TxnType, PayoutStatus
from apps.payouts.repositories.merchant_repo import get_balance_breakdown


@pytest.fixture
def merchant(db):
    return Merchant.objects.create(name="Test Merchant")


@pytest.fixture
def bank_account(merchant):
    return BankAccount.objects.create(
        merchant=merchant, ifsc="HDFC0001234", account_number="50100123456789", label="Primary"
    )


@pytest.fixture
def payout(merchant, bank_account):
    return Payout.objects.create(
        merchant=merchant, bank_account=bank_account, amount_paise=30_000, status=PayoutStatus.PROCESSING
    )


def test_balance_aggregation_all_types(merchant, payout):
    # credits: 100_000 + 50_000 = 150_000
    Transaction.objects.create(merchant=merchant, type=TxnType.CREDIT, amount_paise=100_000)
    Transaction.objects.create(merchant=merchant, type=TxnType.CREDIT, amount_paise=50_000)
    # hold: 30_000
    Transaction.objects.create(merchant=merchant, payout=payout, type=TxnType.HOLD, amount_paise=30_000)
    # release: 5_000 (partial refund scenario)
    Transaction.objects.create(merchant=merchant, payout=payout, type=TxnType.RELEASE, amount_paise=5_000)
    # debit: 25_000
    Transaction.objects.create(merchant=merchant, payout=payout, type=TxnType.DEBIT, amount_paise=25_000)

    result = get_balance_breakdown(str(merchant.id))

    # available = credits - holds + releases - debits
    #           = 150_000 - 30_000 + 5_000 - 25_000 = 100_000
    assert result.available_paise == 100_000
    # held = holds - releases - debits = 30_000 - 5_000 - 25_000 = 0
    assert result.held_paise == 0
    # total_credits = 150_000
    assert result.total_credits_paise == 150_000


def test_balance_zero_for_new_merchant(merchant):
    result = get_balance_breakdown(str(merchant.id))
    assert result.available_paise == 0
    assert result.held_paise == 0
    assert result.total_credits_paise == 0


from apps.payouts.repositories import transaction_repo


def test_insert_credit_updates_balance(merchant):
    transaction_repo.insert_credit(str(merchant.id), 10_000)
    result = get_balance_breakdown(str(merchant.id))
    assert result.available_paise == 10_000
    assert result.total_credits_paise == 10_000


def test_insert_hold_reduces_available(merchant, bank_account):
    transaction_repo.insert_credit(str(merchant.id), 50_000)
    payout = Payout.objects.create(
        merchant=merchant, bank_account=bank_account, amount_paise=20_000, status=PayoutStatus.PROCESSING
    )
    transaction_repo.insert_hold(payout, 20_000)
    result = get_balance_breakdown(str(merchant.id))
    assert result.available_paise == 30_000
    assert result.held_paise == 20_000


def test_insert_release_restores_available(merchant, bank_account):
    transaction_repo.insert_credit(str(merchant.id), 50_000)
    payout = Payout.objects.create(
        merchant=merchant, bank_account=bank_account, amount_paise=20_000, status=PayoutStatus.PROCESSING
    )
    transaction_repo.insert_hold(payout, 20_000)
    transaction_repo.insert_release(payout, 20_000)
    result = get_balance_breakdown(str(merchant.id))
    assert result.available_paise == 50_000
    assert result.held_paise == 0


def test_insert_debit_settles_hold(merchant, bank_account):
    transaction_repo.insert_credit(str(merchant.id), 50_000)
    payout = Payout.objects.create(
        merchant=merchant, bank_account=bank_account, amount_paise=20_000, status=PayoutStatus.PROCESSING
    )
    transaction_repo.insert_hold(payout, 20_000)
    transaction_repo.insert_debit(payout, 20_000)
    result = get_balance_breakdown(str(merchant.id))
    assert result.available_paise == 10_000
    assert result.held_paise == 0
