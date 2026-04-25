import pytest
from rest_framework.test import APIClient
from apps.merchants.models import Merchant
from apps.payouts.repositories import transaction_repo


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def merchant(db):
    return Merchant.objects.create(name="Txn API Merchant")


def test_transactions_list(client, merchant):
    transaction_repo.insert_credit(str(merchant.id), 10_000)
    transaction_repo.insert_credit(str(merchant.id), 20_000)
    response = client.get(f"/api/v1/merchants/{merchant.id}/transactions/")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 2
    assert len(data["results"]) == 2


def test_transactions_pagination(client, merchant):
    for _ in range(5):
        transaction_repo.insert_credit(str(merchant.id), 1_000)
    response = client.get(f"/api/v1/merchants/{merchant.id}/transactions/?limit=2&offset=0")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 5
    assert len(data["results"]) == 2
