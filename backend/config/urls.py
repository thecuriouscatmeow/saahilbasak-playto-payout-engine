from django.http import JsonResponse
from django.urls import path, include
from apps.payouts.api.bank_simulator import BankSimulatorSettleView


def health(request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("health/", health),
    path("api/v1/merchants/", include("apps.merchants.api.urls")),
    path("api/v1/merchants/", include("apps.payouts.api.urls")),
    path("api/v1/payouts/", include("apps.payouts.api.payout_urls")),
    path("api/v1/webhooks/", include("apps.payouts.api.webhook_urls")),
    path("api/v1/bank-simulator/settle/", BankSimulatorSettleView.as_view(), name="bank-simulator-settle"),
]
