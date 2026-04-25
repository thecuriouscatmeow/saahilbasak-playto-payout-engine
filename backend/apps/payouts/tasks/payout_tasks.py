from celery import shared_task
from observability.correlation import bind_correlation_id
from apps.payouts.services.process_payout import ProcessPayoutService


@shared_task(name="payouts.process_payout", bind=True, max_retries=0)
def process_payout(self, payout_id: str, correlation_id: str = ""):
    with bind_correlation_id(correlation_id or self.request.id):
        ProcessPayoutService(payout_id).execute()
