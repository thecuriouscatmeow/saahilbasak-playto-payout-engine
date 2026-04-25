import pytest
from django.core.management import call_command
from apps.payouts.services.reconcile_ledger import ReconcileLedgerService


@pytest.mark.django_db(transaction=True)
def test_stress_smoke_clean_ledger():
    """Tiny stress run: 2 merchants, 4 workers, 2s — ledger must be clean after."""
    call_command(
        "stress_concurrency",
        merchants=2,
        workers=4,
        duration=2,
        per_merchant_credit=500_000,
        verbosity=0,
    )
    report = ReconcileLedgerService().execute()
    assert report.is_clean(), f"Drift detected: {[d.issues for d in report.drifts]}"
