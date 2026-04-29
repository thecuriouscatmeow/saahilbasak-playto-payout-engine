# 01-API_AND_INTERFACE_CONTRACTS

## Contract Truth Rules
This document follows the explicit source priority for conflicts: runtime code, passing tests, migrations and DB constraints, config and settings, existing docs, then comments. If two sources still disagree after that, the disagreement is called out instead of normalized away. Evidence: implementation rule from the requested plan; runtime sources used here include `backend/config/urls.py::urlpatterns`, `backend/apps/payouts/api/views.py`, `backend/apps/merchants/api/views.py`, `frontend/src/api/client.ts::fetchJson`.

## Route Map
### Health
- `GET /health/`
  Returns `{"status": "ok"}` with no auth or headers required. Evidence: `backend/config/urls.py::health`.

### Merchant-Scoped Routes
- `GET /api/v1/merchants/`
  Lists merchants ordered by name. Response shape is an array of `{id, name}` objects. Evidence: `backend/config/urls.py::urlpatterns`, `backend/apps/merchants/api/urls.py::urlpatterns`, `backend/apps/merchants/api/views.py::MerchantListView`, `backend/apps/merchants/api/serializers.py::MerchantSerializer`.
- `GET /api/v1/merchants/{merchant_id}/bank_accounts/`
  Lists active bank accounts ordered by `created_at`. Account numbers are masked to `XXXX` plus the last four digits. Evidence: `backend/apps/merchants/api/views.py::BankAccountListView`, `backend/apps/merchants/api/serializers.py::BankAccountSerializer.get_account_number`.
- `GET /api/v1/merchants/{merchant_id}/balance/`
  Returns a ledger-derived balance snapshot: `available_paise`, `held_paise`, `total_credits_paise`. Evidence: `backend/apps/payouts/api/urls.py::urlpatterns`, `backend/apps/payouts/api/views.py::BalanceView`, `backend/apps/payouts/api/serializers.py::BalanceSerializer`, `backend/tests/integration/test_balance_api.py::test_balance_endpoint`.
- `GET /api/v1/merchants/{merchant_id}/transactions/`
  Returns DRF limit-offset pagination with `count`, `next`, `previous`, and `results`, ordered by newest transaction first. Default limit is 50. Evidence: `backend/apps/payouts/api/views.py::TransactionPagination`, `backend/apps/payouts/api/views.py::TransactionListView`, `backend/tests/integration/test_transactions_api.py::test_transactions_list`, `backend/tests/integration/test_transactions_api.py::test_transactions_pagination`.

### Payout Routes
- `POST /api/v1/payouts/`
  Creates a payout request and reserves funds if valid. Evidence: `backend/config/urls.py::urlpatterns`, `backend/apps/payouts/api/payout_urls.py::urlpatterns`, `backend/apps/payouts/api/views.py::PayoutCreateView`.
- `GET /api/v1/payouts/list/`
  Lists payouts for the merchant in `X-Merchant-Id`, newest first, using the same limit-offset paginator class as transactions. Evidence: `backend/apps/payouts/api/views.py::PayoutListView`, `backend/apps/payouts/api/views.py::TransactionPagination`.
- `GET /api/v1/payouts/{id}/`
  Returns a single payout filtered by `X-Merchant-Id`. Evidence: `backend/apps/payouts/api/views.py::PayoutDetailView`.
- `GET /api/v1/payouts/{payout_id}/events/`
  Returns ordered payout event rows with `id`, `from_status`, `to_status`, `note`, and `created_at`. Evidence: `backend/apps/payouts/api/views.py::PayoutEventsView`.

## Payout Creation API
### Required Headers
- `X-Merchant-Id`
  Required by the backend for `POST /api/v1/payouts/`; missing it yields a `400`. Evidence: `backend/apps/payouts/api/views.py::PayoutCreateView.post`, `backend/tests/integration/test_payout_api_contracts.py::test_create_payout_400_missing_headers`.
- `Idempotency-Key`
  Required by the backend for `POST /api/v1/payouts/`; missing it also yields a `400`. The frontend auto-generates one for POSTs if the caller did not supply it. Evidence: `backend/apps/payouts/api/views.py::PayoutCreateView.post`, `frontend/src/api/client.ts::fetchJson`.
- `X-Correlation-Id`
  Optional for all HTTP requests; if present it is echoed back, otherwise middleware generates a UUID. Evidence: `backend/observability/middleware.py::CorrelationIdMiddleware`, `backend/tests/integration/test_correlation_middleware.py::test_response_echoes_provided_correlation_id`, `backend/tests/integration/test_correlation_middleware.py::test_response_generates_correlation_id_if_absent`.

### Request Body
```json
{
  "amount_paise": 10000,
  "bank_account_id": "uuid"
}
```
`amount_paise` must be an integer `>= 1`, and `bank_account_id` must be a UUID. Evidence: `backend/apps/payouts/api/serializers.py::CreatePayoutRequestSerializer`.

### Success Response
On success the endpoint returns `201` with:
```json
{
  "id": "uuid",
  "merchant_id": "uuid",
  "bank_account_id": "uuid",
  "amount_paise": 10000,
  "status": "pending"
}
```
The body comes from `CreatePayoutService._run_critical_path()` and is persisted into the idempotency record for replay. Evidence: `backend/apps/payouts/services/create_payout.py::CreatePayoutService._run_critical_path`, `backend/apps/payouts/repositories/idempotency_repo.py::update_with_response`, `backend/tests/integration/test_payout_api_contracts.py::test_create_payout_201`.

### Validation and Error Responses
- `400` for missing `X-Merchant-Id` or `Idempotency-Key`. Evidence: `backend/apps/payouts/api/views.py::PayoutCreateView.post`, `backend/tests/integration/test_payout_api_contracts.py::test_create_payout_400_missing_headers`.
- `400` for serializer validation errors such as non-positive `amount_paise` or invalid `bank_account_id`. Evidence: `backend/apps/payouts/api/views.py::PayoutCreateView.post`, `backend/apps/payouts/api/serializers.py::CreatePayoutRequestSerializer`.
- `404` if the bank account does not exist for that merchant or is inactive. Evidence: `backend/apps/payouts/services/create_payout.py::CreatePayoutService._run_critical_path`, `backend/apps/payouts/api/exceptions.py::custom_exception_handler`.
- `409` with `{"error": "key_reused_with_different_body", "idempotency_key": ...}` when the same merchant and key are reused with a different canonical body hash. Evidence: `backend/apps/payouts/services/create_payout.py::CreatePayoutService._handle_existing_record`, `backend/apps/payouts/api/exceptions.py::custom_exception_handler`, `backend/tests/integration/test_payout_api_contracts.py::test_create_payout_409_idempotency_mismatch`.
- `422` with `error`, `available_paise`, and `requested_paise` if derived available balance is too low. Evidence: `backend/apps/payouts/services/create_payout.py::CreatePayoutService._run_critical_path`, `backend/apps/payouts/api/exceptions.py::custom_exception_handler`, `backend/tests/integration/test_payout_api_contracts.py::test_create_payout_422_insufficient_balance`.

## Idempotency Behavior
The backend materializes idempotency with a unique constraint on `(merchant, idempotency_key)` plus a stored `request_hash`, `state`, optional `payout`, serialized response body, and expiry timestamp. Evidence: `backend/apps/payouts/models.py::IdempotencyRecord`, `backend/tests/integration/test_db_constraints.py::test_idempotency_unique_key_constraint`.

When a key is new, the service inserts an `in_flight` record, runs payout creation, and stores a completed response with a private `_status` field for exact replay. Evidence: `backend/apps/payouts/repositories/idempotency_repo.py::insert_or_get_by_key`, `backend/apps/payouts/repositories/idempotency_repo.py::update_with_response`, `backend/apps/payouts/services/create_payout.py::CreatePayoutService.execute`.

When a key already exists:
- Matching `request_hash` + completed state returns the stored response and original status. Evidence: `backend/apps/payouts/services/create_payout.py::CreatePayoutService._handle_existing_record`, `backend/tests/integration/test_idempotency_replay.py::test_idempotency_replay_returns_same_response`.
- Matching `request_hash` + still `in_flight` causes up to five polls with `time.sleep(0.2)`; if the first request still has not completed, the second caller gets `202` with `{"status":"in_flight","idempotency_key":...,"retry_after_ms":1000}`. Evidence: `backend/apps/payouts/services/create_payout.py::CreatePayoutService._handle_existing_record`, `backend/tests/integration/test_idempotency_in_flight.py::test_in_flight_second_request_returns_202_or_stored`.
- Different `request_hash` returns `409`. Evidence: `backend/apps/payouts/services/create_payout.py::CreatePayoutService._handle_existing_record`, `backend/tests/integration/test_idempotency_payload_mismatch.py::test_payload_mismatch_raises_409`.

The replay contract is not just semantic; tests assert it does not create a second payout or second hold transaction. Evidence: `backend/tests/integration/test_idempotency_replay.py::test_idempotency_replay_returns_same_response`, `backend/tests/integration/test_idempotency_replay.py::test_idempotency_replay_does_not_double_hold`.

## Balance API Contract
`GET /api/v1/merchants/{merchant_id}/balance/` always returns a 200 with zeroed values for a new merchant rather than a not-found-style empty response. Evidence: `backend/apps/payouts/api/views.py::BalanceView`, `backend/tests/integration/test_balance_api.py::test_balance_zero_new_merchant`.

The returned shape is:
```json
{
  "available_paise": 50000,
  "held_paise": 0,
  "total_credits_paise": 50000
}
```
Evidence: `backend/apps/payouts/api/serializers.py::BalanceSerializer`, `backend/tests/integration/test_balance_api.py::test_balance_endpoint`.

## Merchant and Bank Account Contracts
`GET /api/v1/merchants/` returns an array of merchants, not a paginated wrapper. Evidence: `backend/apps/merchants/api/views.py::MerchantListView`, `backend/apps/merchants/api/serializers.py::MerchantSerializer`.

`GET /api/v1/merchants/{merchant_id}/bank_accounts/` returns active accounts only, with masked account numbers in the response. Evidence: `backend/apps/merchants/api/views.py::BankAccountListView`, `backend/apps/merchants/api/serializers.py::BankAccountSerializer`.

## Transactions Contract
The transactions list response includes:
```json
{
  "count": 2,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": "uuid",
      "type": "credit|hold|release|debit",
      "amount_paise": 10000,
      "payout_id": null,
      "created_at": "timestamp"
    }
  ]
}
```
Evidence: `backend/apps/payouts/api/serializers.py::TransactionSerializer`, `backend/apps/payouts/api/views.py::TransactionListView`, `backend/tests/integration/test_transactions_api.py::test_transactions_list`.

## Payout Read Contracts
Payout list and detail responses expose `id`, `merchant_id`, `bank_account_id`, `amount_paise`, and `status`, with list ordering newest-first. The serializer used in reads does not include `updated_at`, even though the `Payout` model has it. Evidence: `backend/apps/payouts/api/serializers.py::PayoutResponseSerializer`, `backend/apps/payouts/api/views.py::PayoutListView`, `backend/apps/payouts/api/views.py::PayoutDetailView`, `backend/apps/payouts/models.py::Payout`.

Payout events are read directly from `.values(...)` over the `related_name="events"` relation. Evidence: `backend/apps/payouts/models.py::PayoutEvent`, `backend/apps/payouts/api/views.py::PayoutEventsView`.

## Async Contracts
### Celery Task Input
- Task name: `payouts.process_payout`
- Args: `payout_id`
- Kwargs: optional `correlation_id`
- Retry policy: `max_retries=0`
Evidence: `backend/apps/payouts/tasks/payout_tasks.py::process_payout`.

The create-payout service enqueues this task after the DB transaction commits. It passes the current correlation ID if one exists, otherwise the task binds its own request ID. Evidence: `backend/apps/payouts/services/create_payout.py::CreatePayoutService._run_critical_path`, `backend/observability/correlation.py::get_correlation_id`, `backend/apps/payouts/tasks/payout_tasks.py::process_payout`.

### Scheduled Jobs
- `payouts.sweep_stale` runs every 10 seconds. Evidence: `backend/config/settings/base.py::CELERY_BEAT_SCHEDULE`, `backend/apps/payouts/tasks/sweep_stale.py::sweep_stale`, `backend/tests/integration/test_celery_config.py::test_beat_schedule_has_sweep_stale`.
- `payouts.expire_idempotency` runs daily at `03:00` server time. Evidence: `backend/config/settings/base.py::CELERY_BEAT_SCHEDULE`, `backend/apps/payouts/tasks/expire_idempotency.py::expire_idempotency`, `backend/tests/integration/test_celery_config.py::test_beat_schedule_has_expire_idempotency`.

## Frontend Contracts
### Shared Types
Frontend shared contracts are declared in `frontend/src/api/types.ts`. They include `Merchant`, `BankAccount`, `Balance`, `Transaction`, `Payout`, `PaginatedResponse<T>`, and `ApiErrorBody`. Evidence: `frontend/src/api/types.ts`.

### API Client Behavior
`fetchJson()` always sets `Content-Type: application/json`, injects the current merchant ID from a setter-backed getter, and auto-adds an `Idempotency-Key` for POSTs if one is absent. Evidence: `frontend/src/api/client.ts::fetchJson`, `frontend/src/hooks/useMerchant.ts::useMerchant`.

### Hooks and Polling
- `useBalance(merchantId)` fetches immediately and then polls every 3000 ms through `usePolling()`. Evidence: `frontend/src/hooks/useBalance.ts::useBalance`, `frontend/src/hooks/usePolling.ts::usePolling`, `frontend/src/utils/constants.ts::POLL_INTERVAL_MS`.
- `usePayouts(merchantId)` has the same polling behavior. Evidence: `frontend/src/hooks/usePayouts.ts::usePayouts`, `frontend/src/hooks/usePolling.ts::usePolling`.
- `useTransactions(merchantId)` fetches on dependency change but does not poll. Evidence: `frontend/src/hooks/useTransactions.ts::useTransactions`.
- `useCreatePayout()` maps `ApiError` with `insufficient_balance` into a human-readable INR string using `available_paise`. Evidence: `frontend/src/hooks/useCreatePayout.ts::useCreatePayout`.

### Dashboard Surface
There is an internal `get_dashboard()` service in the backend, but no public HTTP dashboard endpoint is mounted in `backend/config/urls.py`. The UI composes dashboard behavior client-side by calling separate merchant, balance, payout, and transaction endpoints. Evidence: `backend/apps/payouts/services/dashboard.py::get_dashboard`, `backend/config/urls.py::urlpatterns`, `frontend/src/App.tsx::App`.

## Known Unknowns
- The prompt asks for "dashboard endpoints," but the runtime code only exposes a dashboard service helper, not an HTTP route. This document treats dashboard behavior as composed contracts, not an API endpoint. Evidence: `backend/apps/payouts/services/dashboard.py::get_dashboard`, `backend/config/urls.py::urlpatterns`. Confidence: High.
- The payout create response body omits `updated_at`, while frontend `Payout` type includes it. This is a real shape mismatch risk for create responses versus read responses because the frontend reuses one type for both. Evidence: `backend/apps/payouts/services/create_payout.py::CreatePayoutService._run_critical_path`, `frontend/src/api/types.ts::Payout`. Confidence: High.
- The idempotency polling contract returns `202` after one second of total sleep, but there is no documented client retry loop beyond exposing the error/success state. Whether the UI should special-case `in_flight` responses is not encoded in hooks. Evidence: `backend/apps/payouts/services/create_payout.py::CreatePayoutService._handle_existing_record`, `frontend/src/hooks/useCreatePayout.ts::useCreatePayout`. Confidence: Medium.
- The API has no authentication or authorization layer beyond merchant ID headers and path parameters in this repo snapshot. Whether that is intentional for interview scope or omitted for brevity is not proven. Evidence: `backend/config/settings/base.py::MIDDLEWARE`, absence of DRF auth settings. Confidence: Medium.
