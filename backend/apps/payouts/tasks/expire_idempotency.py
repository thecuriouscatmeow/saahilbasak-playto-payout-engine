from celery import shared_task
from apps.payouts.repositories import idempotency_repo


@shared_task(name="payouts.expire_idempotency")
def expire_idempotency():
    count = idempotency_repo.purge_expired()
    return {"purged": count}
