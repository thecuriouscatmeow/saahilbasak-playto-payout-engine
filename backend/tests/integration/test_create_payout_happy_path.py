import pytest
from apps.merchants.models import Merchant, BankAccount
from apps.payouts.models import Payout, Transaction
from apps.payouts.repositories import transaction_repo
from apps.payouts.domain.enums import TxnType, PayoutStatus
from apps.payouts.services.create_payout import CreatePayoutService
import uuid


@pytest.fixture
def merchant(db):
    return Merchant.objects.create(name="Happy Path Merchant")


@pytest.fixture
def bank_account(merchant):
    return BankAccount.objects.create(
        merchant=merchant, ifsc="HDFC0001234", account_number="50100123456789", label="Primary"
    )


@pytest.fixture
def funded_merchant(merchant):
    transaction_repo.insert_credit(str(merchant.id), 100_000)
    return merchant


def test_happy_path_creates_payout_and_hold(funded_merchant, bank_account):
    svc = CreatePayoutService(
        merchant_id=str(funded_merchant.id),
        amount_paise=30_000,
        bank_account_id=str(bank_account.id),
        idempotency_key=str(uuid.uuid4()),
        raw_body={"amount_paise": 30_000, "bank_account_id": str(bank_account.id)},
    )
    status, body = svc.execute()

    assert status == 201
    assert body["amount_paise"] == 30_000
    assert body["status"] == PayoutStatus.PENDING

    assert Payout.objects.count() == 1
    assert Transaction.objects.filter(type=TxnType.HOLD).count() == 1


def test_insufficient_balance_raises(merchant, bank_account):
    from apps.payouts.domain.errors import InsufficientBalance
    transaction_repo.insert_credit(str(merchant.id), 1_000)

    svc = CreatePayoutService(
        merchant_id=str(merchant.id),
        amount_paise=5_000,
        bank_account_id=str(bank_account.id),
        idempotency_key=str(uuid.uuid4()),
        raw_body={"amount_paise": 5_000, "bank_account_id": str(bank_account.id)},
    )
    with pytest.raises(InsufficientBalance):
        svc.execute()


def test_bank_account_not_found_raises(funded_merchant):
    from apps.payouts.domain.errors import BankAccountNotFound
    svc = CreatePayoutService(
        merchant_id=str(funded_merchant.id),
        amount_paise=1_000,
        bank_account_id=str(uuid.uuid4()),
        idempotency_key=str(uuid.uuid4()),
        raw_body={"amount_paise": 1_000, "bank_account_id": "nonexistent"},
    )
    with pytest.raises(BankAccountNotFound):
        svc.execute()
