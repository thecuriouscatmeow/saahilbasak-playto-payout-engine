from rest_framework.views import APIView
from rest_framework.generics import ListAPIView, RetrieveAPIView, get_object_or_404
from rest_framework.response import Response
from rest_framework.pagination import LimitOffsetPagination
from apps.payouts.repositories.merchant_repo import get_balance_breakdown
from apps.payouts.models import Transaction, Payout
from apps.payouts.services.create_payout import CreatePayoutService
from apps.payouts.api.serializers import (
    BalanceSerializer,
    TransactionSerializer,
    PayoutResponseSerializer,
    CreatePayoutRequestSerializer,
)


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


class PayoutCreateView(APIView):
    def post(self, request):
        merchant_id = request.headers.get("X-Merchant-Id")
        idempotency_key = request.headers.get("Idempotency-Key")
        if not merchant_id or not idempotency_key:
            return Response(
                {"error": "X-Merchant-Id and Idempotency-Key headers required"}, status=400
            )

        serializer = CreatePayoutRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=400)

        svc = CreatePayoutService(
            merchant_id=merchant_id,
            amount_paise=serializer.validated_data["amount_paise"],
            bank_account_id=str(serializer.validated_data["bank_account_id"]),
            idempotency_key=idempotency_key,
            raw_body=request.data,
        )
        status_code, body = svc.execute()
        return Response(body, status=status_code)


class PayoutListView(ListAPIView):
    serializer_class = PayoutResponseSerializer
    pagination_class = TransactionPagination

    def get_queryset(self):
        merchant_id = self.request.headers.get("X-Merchant-Id")
        return Payout.objects.filter(merchant_id=merchant_id).order_by("-created_at")


class PayoutDetailView(RetrieveAPIView):
    serializer_class = PayoutResponseSerializer
    lookup_field = "id"

    def get_queryset(self):
        merchant_id = self.request.headers.get("X-Merchant-Id")
        return Payout.objects.filter(merchant_id=merchant_id)


class PayoutEventsView(APIView):
    def get(self, request, payout_id):
        payout = get_object_or_404(Payout, id=payout_id)
        events = payout.events.order_by("created_at").values(
            "id", "from_status", "to_status", "note", "created_at"
        )
        return Response(list(events))
