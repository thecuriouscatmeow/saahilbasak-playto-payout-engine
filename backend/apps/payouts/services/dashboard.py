from apps.payouts.repositories.merchant_repo import get_balance_breakdown
from apps.payouts.models import Transaction


def get_dashboard(merchant_id: str) -> dict:
    balance = get_balance_breakdown(merchant_id)
    recent_txns = list(
        Transaction.objects.filter(merchant_id=merchant_id)
        .order_by("-created_at")
        .values("id", "type", "amount_paise", "payout_id", "created_at")[:50]
    )
    return {
        "balance": {
            "available_paise": balance.available_paise,
            "held_paise": balance.held_paise,
            "total_credits_paise": balance.total_credits_paise,
        },
        "recent_transactions": recent_txns,
    }
