import pytest
from rest_framework.test import APIClient
from apps.merchants.models import Merchant


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def merchant(db):
    return Merchant.objects.create(name="Middleware Test Merchant")


def test_response_echoes_provided_correlation_id(client, merchant):
    resp = client.get(
        f"/api/v1/merchants/{merchant.id}/balance/",
        HTTP_X_CORRELATION_ID="my-trace-id-123",
    )
    assert resp.status_code == 200
    assert resp["X-Correlation-Id"] == "my-trace-id-123"


def test_response_generates_correlation_id_if_absent(client, merchant):
    resp = client.get(f"/api/v1/merchants/{merchant.id}/balance/")
    assert resp.status_code == 200
    cid = resp.get("X-Correlation-Id", "")
    assert len(cid) == 36
