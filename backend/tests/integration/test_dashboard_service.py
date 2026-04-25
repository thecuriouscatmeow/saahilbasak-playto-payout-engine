import pytest
from apps.merchants.models import Merchant
from apps.payouts.repositories import transaction_repo
from apps.payouts.services.dashboard import get_dashboard


@pytest.fixture
def merchant(db):
    return Merchant.objects.create(name="Dashboard Test Merchant")


def test_dashboard_structure(merchant):
    transaction_repo.insert_credit(str(merchant.id), 100_000)
    result = get_dashboard(str(merchant.id))

    assert "balance" in result
    assert "recent_transactions" in result
    assert result["balance"]["available_paise"] == 100_000
    assert result["balance"]["total_credits_paise"] == 100_000
    assert len(result["recent_transactions"]) == 1
    assert result["recent_transactions"][0]["type"] == "credit"


def test_dashboard_empty_merchant(merchant):
    result = get_dashboard(str(merchant.id))
    assert result["balance"]["available_paise"] == 0
    assert result["recent_transactions"] == []
