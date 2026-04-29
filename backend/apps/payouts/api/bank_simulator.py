import random
import threading

import httpx
from rest_framework.views import APIView
from rest_framework.response import Response


class BankSimulatorSettleView(APIView):
    """
    Embedded bank simulator endpoint — mirrors the standalone bank_simulator/ FastAPI
    service but runs inside the Django process so Railway free-tier deploys work.

    HTTP boundary is still real: ProcessPayoutService fires httpx.post() here,
    and this view fires httpx.post() back to /api/v1/webhooks/bank-callback/.
    The round-trip is self-referential within the web service but uses the
    same wire protocol as the standalone service.

    In production, replace with an actual external payment provider.
    """

    authentication_classes = []
    permission_classes = []

    def post(self, request):
        payout_id = request.data.get("payout_id")
        amount_paise = request.data.get("amount_paise")
        callback_url = request.data.get("callback_url")

        if not payout_id or not callback_url:
            return Response({"detail": "payout_id and callback_url required"}, status=400)

        r = random.random()
        if r < 0.70:
            outcome = "success"
        elif r < 0.90:
            outcome = "failure"
        else:
            outcome = "pending"

        if outcome != "pending":
            threading.Thread(
                target=self._fire_callback,
                args=(callback_url, payout_id, outcome),
                daemon=True,
            ).start()

        return Response({"accepted": True, "outcome_will_be": outcome})

    @staticmethod
    def _fire_callback(callback_url: str, payout_id: str, outcome: str) -> None:
        import time
        time.sleep(random.uniform(0.1, 0.4))
        try:
            httpx.post(
                callback_url,
                json={"payout_id": payout_id, "outcome": outcome},
                timeout=5.0,
            )
        except Exception:
            pass
