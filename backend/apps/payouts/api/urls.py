from django.urls import path
from apps.payouts.api.views import (
    BalanceView,
    TransactionListView,
)

# Merchant-scoped routes — mounted under api/v1/merchants/
urlpatterns = [
    path("<uuid:merchant_id>/balance/", BalanceView.as_view(), name="balance"),
    path("<uuid:merchant_id>/transactions/", TransactionListView.as_view(), name="transactions"),
]
