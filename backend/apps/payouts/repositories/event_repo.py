from apps.payouts.models import PayoutEvent


def append(payout_id: str, frm: str | None, to: str, reason: str = "") -> PayoutEvent:
    return PayoutEvent.objects.create(
        payout_id=payout_id,
        from_status=frm,
        to_status=to,
        note=reason,
    )
