import uuid
import pytest
from apps.merchants.models import Merchant, BankAccount
from apps.payouts.repositories import transaction_repo
from apps.payouts.services.create_payout import CreatePayoutService
from apps.payouts.domain.errors import IdempotencyPayloadMismatch


@pytest.fixture
def merchant(db):
    return Merchant.objects.create(name="Mismatch Test Merchant")


@pytest.fixture
def bank_account(merchant):
    return BankAccount.objects.create(
        merchant=merchant, ifsc="HDFC0001234", account_number="50100123456789", label="Primary"
    )


@pytest.fixture
def funded_merchant(merchant):
    transaction_repo.insert_credit(str(merchant.id), 100_000)
    return merchant


def test_payload_mismatch_raises_409(funded_merchant, bank_account):
    key = str(uuid.uuid4())
    body_a = {"amount_paise": 10_000, "bank_account_id": str(bank_account.id)}
    body_b = {"amount_paise": 20_000, "bank_account_id": str(bank_account.id)}

    svc_a = CreatePayoutService(
        merchant_id=str(funded_merchant.id),
        amount_paise=10_000,
        bank_account_id=str(bank_account.id),
        idempotency_key=key,
        raw_body=body_a,
    )
    svc_b = CreatePayoutService(
        merchant_id=str(funded_merchant.id),
        amount_paise=20_000,
        bank_account_id=str(bank_account.id),
        idempotency_key=key,
        raw_body=body_b,
    )

    svc_a.execute()
    with pytest.raises(IdempotencyPayloadMismatch):
        svc_b.execute()
