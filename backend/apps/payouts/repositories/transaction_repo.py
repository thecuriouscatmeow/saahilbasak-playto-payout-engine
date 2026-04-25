from apps.payouts.models import Transaction, Payout
from apps.payouts.domain.enums import TxnType


def insert_credit(merchant_id: str, amount_paise: int) -> Transaction:
    return Transaction.objects.create(
        merchant_id=merchant_id,
        type=TxnType.CREDIT,
        amount_paise=amount_paise,
    )


def insert_hold(payout: Payout, amount_paise: int) -> Transaction:
    return Transaction.objects.create(
        merchant_id=payout.merchant_id,
        payout=payout,
        type=TxnType.HOLD,
        amount_paise=amount_paise,
    )


def insert_release(payout: Payout, amount_paise: int) -> Transaction:
    return Transaction.objects.create(
        merchant_id=payout.merchant_id,
        payout=payout,
        type=TxnType.RELEASE,
        amount_paise=amount_paise,
    )


def insert_debit(payout: Payout, amount_paise: int) -> Transaction:
    return Transaction.objects.create(
        merchant_id=payout.merchant_id,
        payout=payout,
        type=TxnType.DEBIT,
        amount_paise=amount_paise,
    )
