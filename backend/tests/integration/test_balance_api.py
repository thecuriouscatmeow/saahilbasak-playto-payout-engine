import pytest
from rest_framework.test import APIClient
from apps.merchants.models import Merchant
from apps.payouts.repositories import transaction_repo


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def merchant(db):
    return Merchant.objects.create(name="Balance API Merchant")


def test_balance_endpoint(client, merchant):
    transaction_repo.insert_credit(str(merchant.id), 50_000)
    response = client.get(f"/api/v1/merchants/{merchant.id}/balance/")
    assert response.status_code == 200
    data = response.json()
    assert data["available_paise"] == 50_000
    assert data["held_paise"] == 0
    assert data["total_credits_paise"] == 50_000


def test_balance_zero_new_merchant(client, merchant):
    response = client.get(f"/api/v1/merchants/{merchant.id}/balance/")
    assert response.status_code == 200
    assert response.json()["available_paise"] == 0
