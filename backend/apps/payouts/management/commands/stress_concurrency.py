import random
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from django.core.management.base import BaseCommand
from django.db import connection
from apps.merchants.models import Merchant, BankAccount
from apps.payouts.repositories import transaction_repo
from apps.payouts.services.create_payout import CreatePayoutService
from apps.payouts.services.reconcile_ledger import ReconcileLedgerService
from apps.payouts.domain.errors import InsufficientBalance, IdempotencyPayloadMismatch


class Command(BaseCommand):
    help = "Stress-test concurrent payout creation and verify ledger integrity"

    def add_arguments(self, parser):
        parser.add_argument("--merchants", type=int, default=3)
        parser.add_argument("--workers", type=int, default=10)
        parser.add_argument("--duration", type=int, default=5)
        parser.add_argument("--per-merchant-credit", type=int, default=1_000_000)

    def handle(self, *args, **options):
        n_merchants = options["merchants"]
        n_workers = options["workers"]
        duration = options["duration"]
        credit = options["per_merchant_credit"]

        self.stdout.write(f"Seeding {n_merchants} merchants with ₹{credit // 100:,} each...")
        merchants = []
        for i in range(n_merchants):
            m = Merchant.objects.create(name=f"Stress Merchant {i}")
            ba = BankAccount.objects.create(
                merchant=m, ifsc="HDFC0001234",
                account_number=f"5010012345{i:04d}", label="Stress Account"
            )
            transaction_repo.insert_credit(str(m.id), credit)
            merchants.append((m, ba))

        import time
        stop_at = time.monotonic() + duration
        counters = {"ok": 0, "insufficient": 0, "mismatch": 0, "error": 0}
        lock = threading.Lock()

        def worker():
            connection.close()
            while time.monotonic() < stop_at:
                merchant, ba = random.choice(merchants)
                amount = random.randint(100, 5_000)
                try:
                    svc = CreatePayoutService(
                        merchant_id=str(merchant.id),
                        amount_paise=amount,
                        bank_account_id=str(ba.id),
                        idempotency_key=str(uuid.uuid4()),
                        raw_body={"amount_paise": amount, "bank_account_id": str(ba.id)},
                    )
                    status, _ = svc.execute()
                    with lock:
                        counters["ok"] += 1
                except InsufficientBalance:
                    with lock:
                        counters["insufficient"] += 1
                except IdempotencyPayloadMismatch:
                    with lock:
                        counters["mismatch"] += 1
                except Exception:
                    with lock:
                        counters["error"] += 1
            connection.close()

        self.stdout.write(f"Running {n_workers} workers for {duration}s...")
        with ThreadPoolExecutor(max_workers=n_workers) as pool:
            futures = [pool.submit(worker) for _ in range(n_workers)]
            for f in as_completed(futures):
                f.result()

        self.stdout.write(
            f"Results: ok={counters['ok']} insufficient={counters['insufficient']} "
            f"mismatch={counters['mismatch']} errors={counters['error']}"
        )

        self.stdout.write("Running reconciliation...")
        report = ReconcileLedgerService().execute()
        if report.is_clean():
            self.stdout.write(self.style.SUCCESS("Reconcile: CLEAN"))
        else:
            self.stdout.write(self.style.ERROR("Reconcile: DRIFT DETECTED"))
            for d in report.drifts:
                for issue in d.issues:
                    self.stdout.write(f"  {d.merchant_id}: {issue}")
            raise SystemExit(1)
