from django.db.models import F
from django.utils import timezone
from apps.merchants.models import Merchant, BankAccount
from apps.payouts.models import Payout
from apps.payouts.domain.enums import PayoutStatus
from apps.payouts.domain.transitions import validate
from apps.payouts.domain.errors import InvalidStateTransition
from apps.payouts.repositories import event_repo
from apps.payouts.repositories import transaction_repo


def create_with_hold(
    merchant: Merchant,
    bank_account: BankAccount,
    amount_paise: int,
) -> Payout:
    payout = Payout.objects.create(
        merchant=merchant,
        bank_account=bank_account,
        amount_paise=amount_paise,
        status=PayoutStatus.PENDING,
    )
    transaction_repo.insert_hold(payout, amount_paise)
    return payout


def transition(
    payout_id: str,
    *,
    frm: PayoutStatus,
    to: PayoutStatus,
    on_apply=None,
    reason: str = "",
    increment_attempt: bool = False,
) -> int:
    validate(frm, to)

    update_kwargs = {"status": to}
    if increment_attempt:
        update_kwargs["attempts"] = F("attempts") + 1
        update_kwargs["last_attempted_at"] = timezone.now()

    rows = Payout.objects.filter(id=payout_id, status=frm).update(**update_kwargs)
    if rows == 0:
        raise InvalidStateTransition(frm=frm, to=to)

    event_repo.append(payout_id, frm=frm, to=to, reason=reason)

    if on_apply is not None:
        on_apply()

    return rows


def claim_stale_with_skip_locked(cutoff_dt, max_attempts: int) -> list[Payout]:
    return list(
        Payout.objects.select_for_update(skip_locked=True).filter(
            status=PayoutStatus.PROCESSING,
            last_attempted_at__lt=cutoff_dt,
            attempts__lt=max_attempts,
        )
    )
