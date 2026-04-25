from celery import shared_task


@shared_task(bind=True, max_retries=3)
def process_payout(self, payout_id: str):
    # Implemented in sub-4
    pass
