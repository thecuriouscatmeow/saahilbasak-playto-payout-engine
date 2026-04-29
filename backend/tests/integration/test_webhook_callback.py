import uuid
import pytest
from rest_framework.test import APIClient

from apps.merchants.models import Merchant, BankAccount
from apps.payouts.models import Payout, Transaction
from apps.payouts.repositories import transaction_repo, merchant_repo
from apps.payouts.repositories.payout_repo import create_with_hold, transition
from apps.payouts.domain.enums import PayoutStatus, TxnType

WEBHOOK_URL = "/api/v1/webhooks/bank-callback/"


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def merchant(db):
    return Merchant.objects.create(name="Webhook Test Merchant")


@pytest.fixture
def bank_account(merchant):
    return BankAccount.objects.create(
        merchant=merchant,
        ifsc="ICIC0001234",
        account_number="10010100123456",
        label="Primary",
    )


@pytest.fixture
def processing_payout(merchant, bank_account):
    """Create a payout that has been advanced to PROCESSING state."""
    transaction_repo.insert_credit(str(merchant.id), 50_000)
    payout = create_with_hold(merchant, bank_account, 20_000)
    transition(str(payout.id), frm=PayoutStatus.PENDING, to=PayoutStatus.PROCESSING)
    payout.refresh_from_db()
    return payout


# ---------------------------------------------------------------------------
# 1. success callback
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_success_callback(client, processing_payout, merchant):
    resp = client.post(
        WEBHOOK_URL,
        {"payout_id": str(processing_payout.id), "outcome": "success"},
        format="json",
    )
    assert resp.status_code == 200

    processing_payout.refresh_from_db()
    assert processing_payout.status == PayoutStatus.COMPLETED

    assert Transaction.objects.filter(
        payout=processing_payout, type=TxnType.DEBIT
    ).count() == 1

    balance = merchant_repo.get_balance_breakdown(str(merchant.id))
    # credit=50k, hold=20k, debit=20k → held = 0
    assert balance.held_paise == 0


# ---------------------------------------------------------------------------
# 2. failure callback
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_failure_callback(client, processing_payout, merchant):
    resp = client.post(
        WEBHOOK_URL,
        {"payout_id": str(processing_payout.id), "outcome": "failure"},
        format="json",
    )
    assert resp.status_code == 200

    processing_payout.refresh_from_db()
    assert processing_payout.status == PayoutStatus.FAILED

    assert Transaction.objects.filter(
        payout=processing_payout, type=TxnType.RELEASE
    ).count() == 1

    balance = merchant_repo.get_balance_breakdown(str(merchant.id))
    # credit=50k, hold=20k, release=20k → available = 50k, held = 0
    assert balance.held_paise == 0
    assert balance.available_paise == 50_000


# ---------------------------------------------------------------------------
# 3. idempotent re-delivery
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_idempotent_redelivery(client, processing_payout):
    payload = {"payout_id": str(processing_payout.id), "outcome": "success"}

    resp1 = client.post(WEBHOOK_URL, payload, format="json")
    assert resp1.status_code == 200

    txn_count_after_first = Transaction.objects.filter(
        payout=processing_payout, type=TxnType.DEBIT
    ).count()
    assert txn_count_after_first == 1

    resp2 = client.post(WEBHOOK_URL, payload, format="json")
    assert resp2.status_code == 200

    # No duplicate ledger row created on second delivery
    txn_count_after_second = Transaction.objects.filter(
        payout=processing_payout, type=TxnType.DEBIT
    ).count()
    assert txn_count_after_second == txn_count_after_first


# ---------------------------------------------------------------------------
# 4. unknown payout id → 404
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_unknown_payout_id(client, db):
    resp = client.post(
        WEBHOOK_URL,
        {"payout_id": str(uuid.uuid4()), "outcome": "success"},
        format="json",
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 5. malformed body (missing outcome) → 400
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_malformed_body(client, db):
    resp = client.post(
        WEBHOOK_URL,
        {"payout_id": str(uuid.uuid4())},
        format="json",
    )
    assert resp.status_code == 400
