import pytest
from apps.payouts.domain.enums import PayoutStatus
from apps.payouts.domain.errors import InvalidStateTransition
from apps.payouts.domain.transitions import validate


def test_legal_pending_to_processing():
    validate(PayoutStatus.PENDING, PayoutStatus.PROCESSING)  # no exception


def test_legal_processing_to_completed():
    validate(PayoutStatus.PROCESSING, PayoutStatus.COMPLETED)


def test_legal_processing_to_failed():
    validate(PayoutStatus.PROCESSING, PayoutStatus.FAILED)


def test_illegal_pending_to_completed():
    with pytest.raises(InvalidStateTransition):
        validate(PayoutStatus.PENDING, PayoutStatus.COMPLETED)


def test_illegal_failed_to_completed():
    with pytest.raises(InvalidStateTransition):
        validate(PayoutStatus.FAILED, PayoutStatus.COMPLETED)


def test_illegal_completed_to_failed():
    with pytest.raises(InvalidStateTransition):
        validate(PayoutStatus.COMPLETED, PayoutStatus.FAILED)


def test_illegal_same_state():
    with pytest.raises(InvalidStateTransition):
        validate(PayoutStatus.PENDING, PayoutStatus.PENDING)
