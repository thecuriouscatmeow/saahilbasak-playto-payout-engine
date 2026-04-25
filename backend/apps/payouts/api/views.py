from rest_framework.views import APIView
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.pagination import LimitOffsetPagination
from apps.payouts.repositories.merchant_repo import get_balance_breakdown
from apps.payouts.models import Transaction
from apps.payouts.api.serializers import BalanceSerializer, TransactionSerializer


class TransactionPagination(LimitOffsetPagination):
    default_limit = 50


class BalanceView(APIView):
    def get(self, request, merchant_id):
        breakdown = get_balance_breakdown(str(merchant_id))
        return Response(BalanceSerializer(breakdown).data)


class TransactionListView(ListAPIView):
    serializer_class = TransactionSerializer
    pagination_class = TransactionPagination

    def get_queryset(self):
        return Transaction.objects.filter(
            merchant_id=self.kwargs["merchant_id"]
        ).order_by("-created_at")
