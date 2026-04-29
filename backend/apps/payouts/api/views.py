from rest_framework.views import APIView
from rest_framework.generics import ListAPIView, RetrieveAPIView, get_object_or_404
from rest_framework.response import Response
from rest_framework.pagination import LimitOffsetPagination
from apps.payouts.api.authentication import MerchantApiKeyAuthentication
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
    authentication_classes = [MerchantApiKeyAuthentication]
    permission_classes = []

    def post(self, request):
        if request.auth is None:
            return Response({"error": "Authorization required."}, status=401)

        merchant_id = request.auth  # derived from authenticated API key
        idempotency_key = request.headers.get("Idempotency-Key")
        if not idempotency_key:
            return Response({"error": "Idempotency-Key header required"}, status=400)

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
    authentication_classes = [MerchantApiKeyAuthentication]
    permission_classes = []
    serializer_class = PayoutResponseSerializer
    pagination_class = TransactionPagination

    def get_queryset(self):
        if self.request.auth is None:
            return Payout.objects.none()
        return Payout.objects.filter(merchant_id=self.request.auth).order_by("-created_at")


class PayoutDetailView(RetrieveAPIView):
    authentication_classes = [MerchantApiKeyAuthentication]
    permission_classes = []
    serializer_class = PayoutResponseSerializer
    lookup_field = "id"

    def get_queryset(self):
        if self.request.auth is None:
            return Payout.objects.none()
        return Payout.objects.filter(merchant_id=self.request.auth)


class PayoutEventsView(APIView):
    authentication_classes = [MerchantApiKeyAuthentication]
    permission_classes = []

    def get(self, request, payout_id):
        if request.auth is None:
            return Response({"error": "Authorization required."}, status=401)
        payout = get_object_or_404(Payout, id=payout_id, merchant_id=request.auth)
        events = payout.events.order_by("created_at").values(
            "id", "from_status", "to_status", "note", "created_at"
        )
        return Response(list(events))
