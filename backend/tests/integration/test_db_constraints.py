import pytest
from django.db import IntegrityError, transaction
from apps.merchants.models import Merchant, BankAccount
from apps.payouts.models import Transaction, Payout, IdempotencyRecord
from apps.payouts.domain.enums import TxnType, PayoutStatus, IdempotencyState
import uuid
from django.utils import timezone
from datetime import timedelta


@pytest.fixture
def merchant(db):
    return Merchant.objects.create(name="Test Merchant")


@pytest.fixture
def bank_account(merchant):
    return BankAccount.objects.create(
        merchant=merchant, ifsc="HDFC0001234", account_number="1234567890", label="Primary"
    )


@pytest.fixture
def payout(merchant, bank_account):
    return Payout.objects.create(merchant=merchant, bank_account=bank_account, amount_paise=10000)


def test_transaction_negative_amount_rejected(merchant, payout, db):
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Transaction.objects.create(
                merchant=merchant, payout=payout, type=TxnType.HOLD, amount_paise=-100
            )


def test_transaction_invalid_type_rejected(merchant, payout, db):
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Transaction.objects.create(
                merchant=merchant, payout=payout, type="wire", amount_paise=100
            )


def test_credit_with_payout_rejected(merchant, payout, db):
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Transaction.objects.create(
                merchant=merchant, payout=payout, type=TxnType.CREDIT, amount_paise=100
            )


def test_hold_without_payout_rejected(merchant, db):
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Transaction.objects.create(
                merchant=merchant, payout=None, type=TxnType.HOLD, amount_paise=100
            )


def test_payout_negative_amount_rejected(merchant, bank_account, db):
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Payout.objects.create(merchant=merchant, bank_account=bank_account, amount_paise=-500)


def test_idempotency_unique_key_constraint(merchant, db):
    expires = timezone.now() + timedelta(hours=24)
    IdempotencyRecord.objects.create(
        merchant=merchant,
        idempotency_key="key-1",
        request_hash="a" * 64,
        state=IdempotencyState.IN_FLIGHT,
        expires_at=expires,
    )
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            IdempotencyRecord.objects.create(
                merchant=merchant,
                idempotency_key="key-1",
                request_hash="b" * 64,
                state=IdempotencyState.IN_FLIGHT,
                expires_at=expires,
            )
