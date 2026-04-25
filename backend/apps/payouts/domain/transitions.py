from .enums import PayoutStatus
from .errors import InvalidStateTransition

LEGAL = {
    (PayoutStatus.PENDING, PayoutStatus.PROCESSING),
    (PayoutStatus.PROCESSING, PayoutStatus.COMPLETED),
    (PayoutStatus.PROCESSING, PayoutStatus.FAILED),
}


def validate(frm: PayoutStatus, to: PayoutStatus) -> None:
    if (frm, to) not in LEGAL:
        raise InvalidStateTransition(frm=frm, to=to)
