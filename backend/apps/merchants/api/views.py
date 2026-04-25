from rest_framework.generics import ListAPIView, RetrieveAPIView
from apps.merchants.models import Merchant, BankAccount
from apps.merchants.api.serializers import MerchantSerializer, BankAccountSerializer


class MerchantListView(ListAPIView):
    queryset = Merchant.objects.all().order_by("name")
    serializer_class = MerchantSerializer


class BankAccountListView(ListAPIView):
    serializer_class = BankAccountSerializer

    def get_queryset(self):
        return BankAccount.objects.filter(
            merchant_id=self.kwargs["merchant_id"], is_active=True
        ).order_by("created_at")
