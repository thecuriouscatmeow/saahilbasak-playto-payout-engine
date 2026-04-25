import pytest
from apps.merchants.models import Merchant, BankAccount
from apps.payouts.models import Payout, Transaction
from apps.payouts.repositories import transaction_repo
from apps.payouts.domain.enums import PayoutStatus, TxnType
from apps.payouts.services.reconcile_ledger import ReconcileLedgerService
from apps.payouts.services.process_payout import ProcessPayoutService
from apps.payouts.repositories.payout_repo import create_with_hold


@pytest.fixture
def merchant(db):
    return Merchant.objects.create(name="Reconcile Test Merchant")


@pytest.fixture
def bank_account(merchant):
    return BankAccount.objects.create(
        merchant=merchant, ifsc="HDFC0001234", account_number="50100123456789", label="Primary"
    )


@pytest.fixture
def funded_merchant(merchant):
    transaction_repo.insert_credit(str(merchant.id), 100_000)
    return merchant


def test_reconcile_clean_after_completed_payout(funded_merchant, bank_account):
    payout = create_with_hold(funded_merchant, bank_account, 20_000)
    ProcessPayoutService(str(payout.id), settlement_seed=0.5).execute()  # success

    report = ReconcileLedgerService().execute()
    assert report.is_clean(), f"Expected clean, got drifts: {report.drifts}"


def test_reconcile_clean_after_failed_payout(funded_merchant, bank_account):
    payout = create_with_hold(funded_merchant, bank_account, 20_000)
    ProcessPayoutService(str(payout.id), settlement_seed=0.85).execute()  # fail

    report = ReconcileLedgerService().execute()
    assert report.is_clean(), f"Expected clean, got drifts: {report.drifts}"


def test_reconcile_detects_orphan_release(funded_merchant, bank_account):
    """Inject a spurious release on a completed payout → drift detected."""
    payout = create_with_hold(funded_merchant, bank_account, 20_000)
    ProcessPayoutService(str(payout.id), settlement_seed=0.5).execute()  # completed

    # Inject an extra release (simulates a bug)
    Transaction.objects.create(
        merchant=funded_merchant,
        payout=payout,
        type=TxnType.RELEASE,
        amount_paise=20_000,
    )

    report = ReconcileLedgerService().execute()
    assert not report.is_clean()
    issues_text = " ".join(report.drifts[0].issues)
    assert "release" in issues_text
