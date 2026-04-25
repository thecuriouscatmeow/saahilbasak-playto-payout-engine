from celery import shared_task
from apps.payouts.services.retry_stale import RetryStalePayoutsService


@shared_task(name="payouts.sweep_stale")
def sweep_stale():
    count = RetryStalePayoutsService().execute()
    return {"swept": count}
