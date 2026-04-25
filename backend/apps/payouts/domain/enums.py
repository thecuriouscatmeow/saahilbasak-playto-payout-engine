from django.db import models


class PayoutStatus(models.TextChoices):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class TxnType(models.TextChoices):
    CREDIT = "credit"
    HOLD = "hold"
    RELEASE = "release"
    DEBIT = "debit"


class IdempotencyState(models.TextChoices):
    IN_FLIGHT = "in_flight"
    COMPLETED = "completed"
