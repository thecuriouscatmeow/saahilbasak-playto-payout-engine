from dataclasses import dataclass
from django.db.models import Sum, Case, When, Value, F, IntegerField
from apps.merchants.models import Merchant
from apps.payouts.models import Transaction


@dataclass
class BalanceBreakdown:
    available_paise: int
    held_paise: int
    total_credits_paise: int


def lock_for_update(merchant_id: str) -> Merchant:
    return Merchant.objects.select_for_update().get(id=merchant_id)


def get_balance_breakdown(merchant_id: str) -> BalanceBreakdown:
    row = Transaction.objects.filter(merchant_id=merchant_id).aggregate(
        credits=Sum(
            Case(When(type="credit", then=F("amount_paise")), default=Value(0), output_field=IntegerField())
        ),
        holds=Sum(
            Case(When(type="hold", then=F("amount_paise")), default=Value(0), output_field=IntegerField())
        ),
        releases=Sum(
            Case(When(type="release", then=F("amount_paise")), default=Value(0), output_field=IntegerField())
        ),
        debits=Sum(
            Case(When(type="debit", then=F("amount_paise")), default=Value(0), output_field=IntegerField())
        ),
    )
    credits = row["credits"] or 0
    holds = row["holds"] or 0
    releases = row["releases"] or 0
    debits = row["debits"] or 0

    return BalanceBreakdown(
        available_paise=credits - holds + releases - debits,
        held_paise=holds - releases - debits,
        total_credits_paise=credits,
    )
