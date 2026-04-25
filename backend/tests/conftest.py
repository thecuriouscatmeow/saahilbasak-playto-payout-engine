import pytest
from apps.merchants.models import Merchant, BankAccount
from apps.payouts.models import Transaction
from apps.payouts.domain.enums import TxnType


@pytest.fixture
def merchant(db):
    return Merchant.objects.create(name="Acme Exports Pvt Ltd")


@pytest.fixture
def bank_account(merchant):
    return BankAccount.objects.create(
        merchant=merchant,
        ifsc="HDFC0001234",
        account_number="50100123456789",
        label="Current Account",
    )


@pytest.fixture
def seeded_credits(merchant):
    Transaction.objects.create(merchant=merchant, type=TxnType.CREDIT, amount_paise=5_000_000)
    Transaction.objects.create(merchant=merchant, type=TxnType.CREDIT, amount_paise=3_000_000)
    return merchant
