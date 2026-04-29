from django.conf import settings
from django.db import transaction as db_transaction
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from apps.payouts.models import Payout
from apps.payouts.domain.enums import PayoutStatus
from apps.payouts.domain.errors import InvalidStateTransition
from apps.payouts.repositories import payout_repo, transaction_repo


TERMINAL_STATES = {PayoutStatus.COMPLETED, PayoutStatus.FAILED}


class BankCallbackView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        # Validate shared secret when BANK_WEBHOOK_SECRET is configured.
        secret = getattr(settings, "BANK_WEBHOOK_SECRET", "")
        if secret:
            auth = request.headers.get("Authorization", "")
            if auth != f"Bearer {secret}":
                return Response({"detail": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)
        payout_id = request.data.get("payout_id")
        outcome = request.data.get("outcome")

        if not payout_id or outcome not in ("success", "failure"):
            return Response(
                {"detail": "payout_id and outcome ('success'|'failure') are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            payout = Payout.objects.get(id=payout_id)
        except Payout.DoesNotExist:
            return Response({"detail": "Payout not found."}, status=status.HTTP_404_NOT_FOUND)

        # Idempotent re-delivery — already in a terminal state, nothing to do.
        if payout.status in TERMINAL_STATES:
            return Response({"detail": "already handled"}, status=status.HTTP_200_OK)

        with db_transaction.atomic():
            if outcome == "success":
                payout_repo.transition(
                    str(payout.id),
                    frm=PayoutStatus.PROCESSING,
                    to=PayoutStatus.COMPLETED,
                    on_apply=lambda: transaction_repo.insert_debit(payout, payout.amount_paise),
                    reason="bank_settled",
                )
            else:
                payout_repo.transition(
                    str(payout.id),
                    frm=PayoutStatus.PROCESSING,
                    to=PayoutStatus.FAILED,
                    on_apply=lambda: transaction_repo.insert_release(payout, payout.amount_paise),
                    reason="bank_failed",
                )

        return Response({"detail": "ok"}, status=status.HTTP_200_OK)
