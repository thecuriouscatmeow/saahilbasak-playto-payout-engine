from rest_framework import serializers
from apps.merchants.models import Merchant, BankAccount


class MerchantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Merchant
        fields = ["id", "name", "api_key"]


class BankAccountSerializer(serializers.ModelSerializer):
    account_number = serializers.SerializerMethodField()

    class Meta:
        model = BankAccount
        fields = ["id", "ifsc", "account_number", "label", "is_active"]

    def get_account_number(self, obj):
        return f"XXXX{obj.account_number[-4:]}"
