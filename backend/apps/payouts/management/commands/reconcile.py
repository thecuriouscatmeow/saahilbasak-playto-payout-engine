import sys
from django.core.management.base import BaseCommand
from apps.payouts.services.reconcile_ledger import ReconcileLedgerService


class Command(BaseCommand):
    help = "Check ledger ↔ payout invariants and report drift"

    def handle(self, *args, **options):
        report = ReconcileLedgerService().execute()
        if report.is_clean():
            self.stdout.write(self.style.SUCCESS("Reconcile: clean — no drift detected."))
            sys.exit(0)
        else:
            self.stdout.write(self.style.ERROR("Reconcile: DRIFT DETECTED"))
            for d in report.drifts:
                self.stdout.write(f"  Merchant {d.merchant_id}:")
                for issue in d.issues:
                    self.stdout.write(f"    - {issue}")
            sys.exit(1)
