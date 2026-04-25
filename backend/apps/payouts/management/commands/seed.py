from django.core.management.base import BaseCommand
from django.db import transaction
from apps.merchants.models import Merchant, BankAccount
from apps.payouts.models import IdempotencyRecord, Payout, PayoutEvent, Transaction
from apps.payouts.domain.enums import TxnType


SEED_DATA = [
    {
        "name": "Rajesh Textiles Pvt Ltd",
        "accounts": [
            {"ifsc": "HDFC0001234", "account_number": "50100123456789", "label": "Current Account"},
            {"ifsc": "ICIC0005678", "account_number": "001234567890", "label": "Savings Account"},
        ],
        "credits_paise": [5_000_000, 8_000_000, 3_500_000],
    },
    {
        "name": "Priya Pharma Exports",
        "accounts": [
            {"ifsc": "SBIN0009876", "account_number": "20123456789012", "label": "Trade Account"},
        ],
        "credits_paise": [12_000_000, 7_500_000],
    },
    {
        "name": "Coastal Spices Ltd",
        "accounts": [
            {"ifsc": "AXIS0004321", "account_number": "9150123456789", "label": "Current Account"},
            {"ifsc": "KKBK0002222", "account_number": "1234123412341", "label": "Export Account"},
        ],
        "credits_paise": [20_000_000, 15_000_000, 5_000_000],
    },
]


class Command(BaseCommand):
    help = "Seed merchants, bank accounts, and credit transactions"

    def handle(self, *args, **options):
        with transaction.atomic():
            # Delete in FK-safe order: dependents first, then merchants
            IdempotencyRecord.objects.all().delete()
            PayoutEvent.objects.all().delete()
            Transaction.objects.all().delete()
            Payout.objects.all().delete()
            BankAccount.objects.all().delete()
            Merchant.objects.all().delete()

            for data in SEED_DATA:
                merchant = Merchant.objects.create(name=data["name"])
                for acc in data["accounts"]:
                    BankAccount.objects.create(merchant=merchant, **acc)
                for amount in data["credits_paise"]:
                    Transaction.objects.create(
                        merchant=merchant,
                        type=TxnType.CREDIT,
                        amount_paise=amount,
                    )
                total_paise = sum(data["credits_paise"])
                self.stdout.write(
                    f"  {merchant.name}: id={merchant.id} balance=₹{total_paise // 100:,}"
                )

        self.stdout.write(self.style.SUCCESS("Seed complete."))
