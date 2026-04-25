import uuid
import pytest
from apps.merchants.models import Merchant, BankAccount
from apps.payouts.models import Payout
from apps.payouts.repositories import transaction_repo
from apps.payouts.services.create_payout import CreatePayoutService


@pytest.fixture
def merchant(db):
    return Merchant.objects.create(name="Replay Test Merchant")


@pytest.fixture
def bank_account(merchant):
    return BankAccount.objects.create(
        merchant=merchant, ifsc="HDFC0001234", account_number="50100123456789", label="Primary"
    )


@pytest.fixture
def funded_merchant(merchant):
    transaction_repo.insert_credit(str(merchant.id), 100_000)
    return merchant


def make_svc(merchant, bank_account, key, amount=10_000):
    body = {"amount_paise": amount, "bank_account_id": str(bank_account.id)}
    return CreatePayoutService(
        merchant_id=str(merchant.id),
        amount_paise=amount,
        bank_account_id=str(bank_account.id),
        idempotency_key=key,
        raw_body=body,
    )


def test_idempotency_replay_returns_same_response(funded_merchant, bank_account):
    key = str(uuid.uuid4())
    status1, body1 = make_svc(funded_merchant, bank_account, key).execute()
    status2, body2 = make_svc(funded_merchant, bank_account, key).execute()

    assert status1 == 201
    assert status2 == 201
    assert body1["id"] == body2["id"]
    assert Payout.objects.count() == 1


def test_idempotency_replay_does_not_double_hold(funded_merchant, bank_account):
    from apps.payouts.models import Transaction
    from apps.payouts.domain.enums import TxnType
    key = str(uuid.uuid4())
    make_svc(funded_merchant, bank_account, key).execute()
    make_svc(funded_merchant, bank_account, key).execute()

    assert Transaction.objects.filter(type=TxnType.HOLD).count() == 1
