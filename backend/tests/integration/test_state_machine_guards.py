import pytest
from django.db import transaction as db_transaction
from apps.merchants.models import Merchant, BankAccount
from apps.payouts.models import Payout, PayoutEvent
from apps.payouts.domain.enums import PayoutStatus
from apps.payouts.domain.errors import InvalidStateTransition
from apps.payouts.repositories import payout_repo


@pytest.fixture
def merchant(db):
    return Merchant.objects.create(name="SM Test Merchant")


@pytest.fixture
def bank_account(merchant):
    return BankAccount.objects.create(
        merchant=merchant, ifsc="HDFC0001234", account_number="50100123456789", label="Primary"
    )


@pytest.fixture
def pending_payout(merchant, bank_account):
    return Payout.objects.create(
        merchant=merchant, bank_account=bank_account, amount_paise=10_000, status=PayoutStatus.PENDING
    )


def test_pending_to_processing_succeeds(pending_payout):
    with db_transaction.atomic():
        payout_repo.transition(str(pending_payout.id), frm=PayoutStatus.PENDING, to=PayoutStatus.PROCESSING)
    pending_payout.refresh_from_db()
    assert pending_payout.status == PayoutStatus.PROCESSING


def test_transition_appends_event(pending_payout):
    with db_transaction.atomic():
        payout_repo.transition(str(pending_payout.id), frm=PayoutStatus.PENDING, to=PayoutStatus.PROCESSING)
    assert PayoutEvent.objects.filter(payout=pending_payout).count() == 1
    event = PayoutEvent.objects.get(payout=pending_payout)
    assert event.from_status == PayoutStatus.PENDING
    assert event.to_status == PayoutStatus.PROCESSING


def test_illegal_pending_to_completed_raises(pending_payout):
    with pytest.raises(InvalidStateTransition):
        with db_transaction.atomic():
            payout_repo.transition(str(pending_payout.id), frm=PayoutStatus.PENDING, to=PayoutStatus.COMPLETED)


def test_illegal_failed_to_completed_raises(merchant, bank_account):
    p = Payout.objects.create(
        merchant=merchant, bank_account=bank_account, amount_paise=5_000, status=PayoutStatus.FAILED
    )
    with pytest.raises(InvalidStateTransition):
        with db_transaction.atomic():
            payout_repo.transition(str(p.id), frm=PayoutStatus.FAILED, to=PayoutStatus.COMPLETED)


def test_on_apply_runs_in_same_atomic(pending_payout):
    side_effects = []

    def callback():
        side_effects.append("ran")

    with db_transaction.atomic():
        payout_repo.transition(
            str(pending_payout.id),
            frm=PayoutStatus.PENDING,
            to=PayoutStatus.PROCESSING,
            on_apply=callback,
        )
    assert side_effects == ["ran"]


def test_on_apply_rollback_on_exception(pending_payout):
    def bad_callback():
        raise RuntimeError("intentional failure")

    with pytest.raises(RuntimeError):
        with db_transaction.atomic():
            payout_repo.transition(
                str(pending_payout.id),
                frm=PayoutStatus.PENDING,
                to=PayoutStatus.PROCESSING,
                on_apply=bad_callback,
            )
    pending_payout.refresh_from_db()
    assert pending_payout.status == PayoutStatus.PENDING


def test_wrong_frm_status_raises(merchant, bank_account):
    p = Payout.objects.create(
        merchant=merchant, bank_account=bank_account, amount_paise=5_000, status=PayoutStatus.PROCESSING
    )
    with pytest.raises(InvalidStateTransition):
        with db_transaction.atomic():
            # frm=PENDING but actual status is PROCESSING — guard must reject
            payout_repo.transition(str(p.id), frm=PayoutStatus.PENDING, to=PayoutStatus.PROCESSING)
