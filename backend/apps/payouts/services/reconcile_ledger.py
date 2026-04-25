from dataclasses import dataclass, field
from uuid import UUID
from django.db.models import Sum, Q
from apps.merchants.models import Merchant
from apps.payouts.models import Payout, Transaction
from apps.payouts.repositories.merchant_repo import get_balance_breakdown
from apps.payouts.domain.enums import PayoutStatus, TxnType


@dataclass
class MerchantDrift:
    merchant_id: str
    issues: list[str] = field(default_factory=list)


@dataclass
class ReconcileReport:
    drifts: list[MerchantDrift] = field(default_factory=list)

    def is_clean(self) -> bool:
        return not self.drifts


class ReconcileLedgerService:
    def execute(self) -> ReconcileReport:
        report = ReconcileReport()
        for merchant in Merchant.objects.all():
            drift = self._check_merchant(str(merchant.id))
            if drift.issues:
                report.drifts.append(drift)
        return report

    def _check_merchant(self, merchant_id: str) -> MerchantDrift:
        drift = MerchantDrift(merchant_id=merchant_id)
        balance = get_balance_breakdown(merchant_id)

        # Expected held = sum of amounts for payouts in pending/processing
        expected_held = (
            Payout.objects.filter(
                merchant_id=merchant_id,
                status__in=[PayoutStatus.PENDING, PayoutStatus.PROCESSING],
            ).aggregate(total=Sum("amount_paise"))["total"]
            or 0
        )
        if balance.held_paise != expected_held:
            drift.issues.append(
                f"held_mismatch: ledger={balance.held_paise}, payouts={expected_held}"
            )

        # For each terminal payout: must have exactly 1 hold + (1 debit XOR 1 release)
        for payout in Payout.objects.filter(
            merchant_id=merchant_id,
            status__in=[PayoutStatus.COMPLETED, PayoutStatus.FAILED],
        ):
            txns = Transaction.objects.filter(payout=payout)
            holds = txns.filter(type=TxnType.HOLD).count()
            debits = txns.filter(type=TxnType.DEBIT).count()
            releases = txns.filter(type=TxnType.RELEASE).count()

            if holds != 1:
                drift.issues.append(f"payout {payout.id}: expected 1 hold, got {holds}")
            if payout.status == PayoutStatus.COMPLETED and debits != 1:
                drift.issues.append(
                    f"payout {payout.id}: completed but debit count={debits}"
                )
            if payout.status == PayoutStatus.FAILED and releases != 1:
                drift.issues.append(
                    f"payout {payout.id}: failed but release count={releases}"
                )
            if debits > 0 and releases > 0:
                drift.issues.append(
                    f"payout {payout.id}: has both debit and release"
                )

        return drift
