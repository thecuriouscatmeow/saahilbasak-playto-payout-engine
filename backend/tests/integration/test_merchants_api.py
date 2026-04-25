import pytest
from rest_framework.test import APIClient
from apps.merchants.models import Merchant, BankAccount


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def merchant(db):
    return Merchant.objects.create(name="API Test Merchant")


@pytest.fixture
def bank_account(merchant):
    return BankAccount.objects.create(
        merchant=merchant, ifsc="HDFC0001234", account_number="50100123456789", label="Primary"
    )


def test_merchant_list(client, merchant):
    response = client.get("/api/v1/merchants/")
    assert response.status_code == 200
    ids = [m["id"] for m in response.json()]
    assert str(merchant.id) in ids


def test_bank_accounts_masked(client, merchant, bank_account):
    response = client.get(f"/api/v1/merchants/{merchant.id}/bank_accounts/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["account_number"] == "XXXX6789"
    assert "50100123456789" not in str(data)
