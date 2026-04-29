import json
import uuid
import pytest
from rest_framework.test import APIClient
from apps.merchants.models import Merchant, BankAccount
from apps.payouts.repositories import transaction_repo


@pytest.fixture
def merchant(db):
    return Merchant.objects.create(name="Log Events Merchant")


@pytest.fixture
def bank_account(merchant):
    return BankAccount.objects.create(
        merchant=merchant, ifsc="HDFC0001234", account_number="50100123456789", label="Primary"
    )


@pytest.fixture
def funded_merchant(merchant):
    transaction_repo.insert_credit(str(merchant.id), 100_000)
    return merchant


def test_payout_created_log_emitted(funded_merchant, bank_account, capsys):
    client = APIClient()
    key = str(uuid.uuid4())
    client.post(
        "/api/v1/payouts/",
        {"amount_paise": 10_000, "bank_account_id": str(bank_account.id)},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {funded_merchant.api_key}",
        HTTP_IDEMPOTENCY_KEY=key,
    )
    out = capsys.readouterr().out
    events = []
    for line in out.splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            pass

    event_names = [e.get("event") for e in events]
    assert "payout.created" in event_names
    created = next(e for e in events if e.get("event") == "payout.created")
    assert "payout_id" in created
    assert "merchant_id" in created
