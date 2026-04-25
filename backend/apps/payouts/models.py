import uuid
from django.db import models
from apps.payouts.domain.enums import PayoutStatus, TxnType, IdempotencyState


class Payout(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey("merchants.Merchant", on_delete=models.PROTECT)
    bank_account = models.ForeignKey("merchants.BankAccount", on_delete=models.PROTECT)
    amount_paise = models.BigIntegerField()
    status = models.CharField(max_length=20, choices=PayoutStatus.choices, default=PayoutStatus.PENDING)
    last_attempted_at = models.DateTimeField(null=True, blank=True)
    attempts = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "payouts"
        indexes = [
            models.Index(fields=["merchant", "-created_at"]),
            models.Index(
                fields=["status", "last_attempted_at"],
                name="payouts_processing_idx",
                condition=models.Q(status="processing"),
            ),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(amount_paise__gt=0), name="payout_amount_positive"),
            models.CheckConstraint(
                condition=models.Q(status__in=[s.value for s in PayoutStatus]),
                name="payout_status_valid",
            ),
        ]


class Transaction(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey("merchants.Merchant", on_delete=models.PROTECT)
    payout = models.ForeignKey(Payout, null=True, blank=True, on_delete=models.PROTECT)
    type = models.CharField(max_length=10, choices=TxnType.choices)
    amount_paise = models.BigIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "transactions"
        indexes = [
            models.Index(fields=["merchant", "-created_at"]),
            models.Index(fields=["payout"]),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(amount_paise__gt=0), name="txn_amount_positive"),
            models.CheckConstraint(
                condition=models.Q(type__in=[t.value for t in TxnType]),
                name="txn_type_valid",
            ),
            # credit txns have no payout; all other types link to a payout
            models.CheckConstraint(
                condition=(
                    models.Q(type="credit", payout__isnull=True)
                    | models.Q(type__in=["hold", "release", "debit"], payout__isnull=False)
                ),
                name="txn_credit_no_payout",
            ),
        ]


class PayoutEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payout = models.ForeignKey(Payout, on_delete=models.CASCADE, related_name="events")
    from_status = models.CharField(max_length=20, null=True, blank=True)
    to_status = models.CharField(max_length=20)
    note = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "payout_events"
        indexes = [
            models.Index(fields=["payout", "created_at"]),
        ]


class IdempotencyRecord(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey("merchants.Merchant", on_delete=models.PROTECT)
    idempotency_key = models.CharField(max_length=255)
    request_hash = models.CharField(max_length=64)
    state = models.CharField(max_length=20, choices=IdempotencyState.choices, default=IdempotencyState.IN_FLIGHT)
    payout = models.ForeignKey(Payout, null=True, blank=True, on_delete=models.SET_NULL)
    response_body = models.JSONField(null=True, blank=True)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "idempotency_records"
        indexes = [
            models.Index(fields=["expires_at"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["merchant", "idempotency_key"], name="idempotency_unique_key"),
            models.CheckConstraint(
                condition=models.Q(state__in=[s.value for s in IdempotencyState]),
                name="idempotency_state_valid",
            ),
        ]
