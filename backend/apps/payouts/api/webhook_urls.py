from django.urls import path
from apps.payouts.api.webhook import BankCallbackView

urlpatterns = [
    path("bank-callback/", BankCallbackView.as_view(), name="bank-callback"),
]
