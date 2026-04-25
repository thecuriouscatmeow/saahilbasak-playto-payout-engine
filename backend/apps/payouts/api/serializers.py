from rest_framework import serializers
from apps.payouts.models import Transaction, Payout


class BalanceSerializer(serializers.Serializer):
    available_paise = serializers.IntegerField()
    held_paise = serializers.IntegerField()
    total_credits_paise = serializers.IntegerField()


class TransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = ["id", "type", "amount_paise", "payout_id", "created_at"]


class PayoutSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payout
        fields = ["id", "amount_paise", "status", "created_at", "updated_at"]
