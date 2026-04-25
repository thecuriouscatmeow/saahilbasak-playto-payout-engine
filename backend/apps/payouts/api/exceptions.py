from rest_framework.views import exception_handler as drf_default_handler
from rest_framework.response import Response
from apps.payouts.domain.errors import (
    InsufficientBalance,
    InvalidStateTransition,
    IdempotencyPayloadMismatch,
    BankAccountNotFound,
)


def custom_exception_handler(exc, context):
    if isinstance(exc, InsufficientBalance):
        return Response(
            {
                "error": "insufficient_balance",
                "available_paise": exc.available_paise,
                "requested_paise": exc.requested_paise,
            },
            status=422,
        )
    if isinstance(exc, InvalidStateTransition):
        return Response(
            {"error": "invalid_state_transition", "from": exc.frm, "to": exc.to},
            status=409,
        )
    if isinstance(exc, IdempotencyPayloadMismatch):
        return Response(
            {"error": "key_reused_with_different_body", "idempotency_key": exc.idempotency_key},
            status=409,
        )
    if isinstance(exc, BankAccountNotFound):
        return Response({"error": "bank_account_not_found", "account_id": exc.account_id}, status=404)

    return drf_default_handler(exc, context)
