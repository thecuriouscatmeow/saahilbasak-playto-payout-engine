import uuid
import pytest
from rest_framework.test import APIClient
from apps.merchants.models import Merchant, BankAccount
from apps.payouts.repositories import transaction_repo


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def merchant(db):
    return Merchant.objects.create(name="API Contract Merchant")


@pytest.fixture
def bank_account(merchant):
    return BankAccount.objects.create(
        merchant=merchant, ifsc="HDFC0001234", account_number="50100123456789", label="Primary"
    )


@pytest.fixture
def funded_merchant(merchant):
    transaction_repo.insert_credit(str(merchant.id), 100_000)
    return merchant


def headers(merchant, key=None):
    return {
        "HTTP_AUTHORIZATION": f"Bearer {merchant.api_key}",
        "HTTP_IDEMPOTENCY_KEY": key or str(uuid.uuid4()),
    }


def test_create_payout_201(client, funded_merchant, bank_account):
    resp = client.post(
        "/api/v1/payouts/",
        {"amount_paise": 10_000, "bank_account_id": str(bank_account.id)},
        format="json",
        **headers(funded_merchant),
    )
    assert resp.status_code == 201
    assert resp.json()["amount_paise"] == 10_000


def test_create_payout_400_missing_headers(client, funded_merchant, bank_account):
    resp = client.post(
        "/api/v1/payouts/",
        {"amount_paise": 10_000, "bank_account_id": str(bank_account.id)},
        format="json",
    )
    assert resp.status_code == 401


def test_create_payout_422_insufficient_balance(client, merchant, bank_account):
    transaction_repo.insert_credit(str(merchant.id), 1_000)
    resp = client.post(
        "/api/v1/payouts/",
        {"amount_paise": 50_000, "bank_account_id": str(bank_account.id)},
        format="json",
        **headers(merchant),
    )
    assert resp.status_code == 422
    assert resp.json()["error"] == "insufficient_balance"


def test_create_payout_409_idempotency_mismatch(client, funded_merchant, bank_account):
    key = str(uuid.uuid4())
    h = {"HTTP_AUTHORIZATION": f"Bearer {funded_merchant.api_key}", "HTTP_IDEMPOTENCY_KEY": key}
    client.post(
        "/api/v1/payouts/",
        {"amount_paise": 10_000, "bank_account_id": str(bank_account.id)},
        format="json",
        **h,
    )
    resp = client.post(
        "/api/v1/payouts/",
        {"amount_paise": 20_000, "bank_account_id": str(bank_account.id)},
        format="json",
        **h,
    )
    assert resp.status_code == 409
    assert resp.json()["error"] == "key_reused_with_different_body"


def test_create_payout_replay_201(client, funded_merchant, bank_account):
    key = str(uuid.uuid4())
    h = {"HTTP_AUTHORIZATION": f"Bearer {funded_merchant.api_key}", "HTTP_IDEMPOTENCY_KEY": key}
    body = {"amount_paise": 5_000, "bank_account_id": str(bank_account.id)}
    r1 = client.post("/api/v1/payouts/", body, format="json", **h)
    r2 = client.post("/api/v1/payouts/", body, format="json", **h)
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["id"] == r2.json()["id"]
