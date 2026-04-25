from django.urls import path
from apps.payouts.api.views import (
    PayoutCreateView,
    PayoutListView,
    PayoutDetailView,
    PayoutEventsView,
)

# Payout-standalone routes — mounted under api/v1/payouts/
urlpatterns = [
    path("", PayoutCreateView.as_view(), name="payout-create"),
    path("list/", PayoutListView.as_view(), name="payout-list"),
    path("<uuid:id>/", PayoutDetailView.as_view(), name="payout-detail"),
    path("<uuid:payout_id>/events/", PayoutEventsView.as_view(), name="payout-events"),
]
