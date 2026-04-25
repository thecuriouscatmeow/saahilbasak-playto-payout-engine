from django.urls import path
from apps.merchants.api.views import MerchantListView, BankAccountListView

urlpatterns = [
    path("", MerchantListView.as_view(), name="merchant-list"),
    path("<uuid:merchant_id>/bank_accounts/", BankAccountListView.as_view(), name="bank-account-list"),
]
