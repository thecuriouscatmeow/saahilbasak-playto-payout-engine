# 03-CODE_OWNERSHIP_AND_FILE_MAP

## How To Read This Map
This file is not a filename dump. Each entry explains why the file exists, what symbols matter, who calls them, what state they mutate, where the sharp edges live, and where to start debugging. Evidence throughout points to exact symbols rather than folder vibes.

## API Entry Points
### `backend/apps/payouts/api/views.py`
- Purpose: HTTP entry layer for balance, transactions, payout create, payout list/detail, and payout events. Evidence: `backend/apps/payouts/api/views.py::BalanceView`, `backend/apps/payouts/api/views.py::TransactionListView`, `backend/apps/payouts/api/views.py::PayoutCreateView`, `backend/apps/payouts/api/views.py::PayoutListView`, `backend/apps/payouts/api/views.py::PayoutDetailView`, `backend/apps/payouts/api/views.py::PayoutEventsView`.
- Main callers: Django URL config through `backend/apps/payouts/api/urls.py` and `backend/apps/payouts/api/payout_urls.py`. Evidence: both `urlpatterns`.
- Mutates what: `PayoutCreateView` is the only mutating endpoint here; it delegates state changes to `CreatePayoutService`. The others are read-only. Evidence: `backend/apps/payouts/api/views.py::PayoutCreateView.post`.
- Danger zones: header handling is manual, so missing `X-Merchant-Id` or `Idempotency-Key` fails before serializer validation; payout list/detail trust header merchant scoping rather than auth middleware. Evidence: `backend/apps/payouts/api/views.py::PayoutCreateView.post`, `backend/apps/payouts/api/views.py::PayoutListView.get_queryset`.
- Debug here first when: HTTP status codes look wrong, pagination is off, a route exists in docs but not in code, or event readouts are missing fields.

### `backend/apps/merchants/api/views.py`
- Purpose: list merchants and active bank accounts used by the frontend selector and payout form. Evidence: `backend/apps/merchants/api/views.py::MerchantListView`, `backend/apps/merchants/api/views.py::BankAccountListView`.
- Main callers: `frontend/src/features/MerchantSelector.tsx::MerchantSelector`, `frontend/src/features/PayoutForm.tsx::PayoutForm`.
- Mutates what: nothing; both are read-only queryset views.
- Danger zones: account-number masking lives in serializer, not here, so a response-shape bug may originate in `serializers.py`. Evidence: `backend/apps/merchants/api/serializers.py::BankAccountSerializer.get_account_number`.
- Debug here first when: merchant dropdown is empty or bank accounts include inactive entries.

## Core Payout Services
### `backend/apps/payouts/services/create_payout.py`
- Purpose: owns idempotency, balance check, merchant row locking, bank-account validation, payout creation, and post-commit task enqueue. Evidence: `backend/apps/payouts/services/create_payout.py::CreatePayoutService`.
- Main callers: `backend/apps/payouts/api/views.py::PayoutCreateView.post`, direct service tests. Evidence: `backend/tests/integration/test_idempotency_replay.py::make_svc`, `backend/tests/integration/test_concurrency_tier1.py::test_concurrency_tier1`.
- Mutates what: `IdempotencyRecord`, `Payout`, `Transaction` hold row, and task queue side effect. Evidence: `backend/apps/payouts/repositories/idempotency_repo.py::insert_or_get_by_key`, `backend/apps/payouts/repositories/payout_repo.py::create_with_hold`, `backend/apps/payouts/tasks/payout_tasks.py::process_payout`.
- Danger zones:
  - request-path `time.sleep()` polling on duplicate in-flight keys
  - bank-account lookup is inline ORM, not repository-wrapped
  - task enqueue happens after DB block exits, so a queue outage after commit leaves a persisted `pending` payout without immediate processing
  Evidence: `backend/apps/payouts/services/create_payout.py::CreatePayoutService._handle_existing_record`, `backend/apps/payouts/services/create_payout.py::CreatePayoutService._run_critical_path`.
- Debug here first when: duplicate-key behavior is odd, balances go negative, or payout rows exist without worker pickup.

### `backend/apps/payouts/services/process_payout.py`
- Purpose: claim a pending payout, move it to `processing`, simulate settlement, then finalize with either `debit` or `release`. Evidence: `backend/apps/payouts/services/process_payout.py::ProcessPayoutService.execute`.
- Main callers: `backend/apps/payouts/tasks/payout_tasks.py::process_payout`, tests for success, failure, and hang. Evidence: `backend/tests/integration/test_worker_success.py::test_success_path`, `backend/tests/integration/test_worker_failure_refund.py::test_failure_atomically_releases`, `backend/tests/integration/test_worker_hang.py`.
- Mutates what: payout status, attempts, last attempted timestamp, payout events, and terminal transaction rows. Evidence: `backend/apps/payouts/repositories/payout_repo.py::transition`, `backend/apps/payouts/repositories/transaction_repo.py::insert_debit`, `backend/apps/payouts/repositories/transaction_repo.py::insert_release`.
- Danger zones:
  - settlement is simulated, so external-bank timing and retries are not modeled
  - `Payout.objects.get()` happens before conditional transition, so concurrent workers rely on the later guarded update
  Evidence: `backend/apps/payouts/services/process_payout.py::simulate_bank_settlement`, `backend/apps/payouts/services/process_payout.py::ProcessPayoutService.execute`.
- Debug here first when: payouts get stuck in `processing`, duplicate terminal mutations appear, or result codes like `already_handled` or `raced` show up.

### `backend/apps/payouts/services/retry_stale.py`
- Purpose: recover payouts left in `processing` beyond the stale threshold by claiming them with `SKIP LOCKED`, then retrying or failing permanently. Evidence: `backend/apps/payouts/services/retry_stale.py::RetryStalePayoutsService`.
- Main callers: `backend/apps/payouts/tasks/sweep_stale.py::sweep_stale`, sweeper tests. Evidence: `backend/tests/integration/test_stale_sweeper.py`.
- Mutates what: payout attempts, `last_attempted_at`, payout status, payout events, and terminal release/debit transaction rows. Evidence: `backend/apps/payouts/services/retry_stale.py::RetryStalePayoutsService._handle_stale`.
- Danger zones:
  - direct `Payout.objects.filter(...).update(...)` bypasses repository transition/event machinery for the intermediate attempt bump
  - max attempts and threshold are hardcoded/defaulted in code
  Evidence: `backend/apps/payouts/services/retry_stale.py::RetryStalePayoutsService._handle_stale`, `backend/apps/payouts/services/retry_stale.py::MAX_ATTEMPTS`.
- Debug here first when: stale payouts do not recover, attempts increment weirdly, or release/debit counts drift after retries.

### `backend/apps/payouts/services/dashboard.py`
- Purpose: aggregate balance plus recent transactions into a simple dictionary. Evidence: `backend/apps/payouts/services/dashboard.py::get_dashboard`.
- Main callers: tests only in this repo snapshot. Evidence: `backend/tests/integration/test_dashboard_service.py::test_dashboard_structure`.
- Mutates what: nothing.
- Danger zones: it looks product-ready but is not exposed over HTTP.
- Debug here first when: someone claims there is a dashboard API route; there is not.

### `backend/apps/payouts/services/reconcile_ledger.py`
- Purpose: detect ledger drift between payout state and transaction reality. Evidence: `backend/apps/payouts/services/reconcile_ledger.py::ReconcileLedgerService`.
- Main callers: reconciliation tests; no scheduled task currently invokes it. Evidence: `backend/tests/integration/test_reconciliation.py`.
- Mutates what: nothing; pure audit/report generation.
- Danger zones: O(n) over merchants and then over terminal payouts, so a future scheduled use would need scale attention.
- Debug here first when: finance invariants feel off or you suspect double release/debit conditions.

## Repository Layer
### `backend/apps/payouts/repositories/merchant_repo.py`
- Purpose: merchant lock acquisition and ledger-derived balance aggregation. Evidence: `backend/apps/payouts/repositories/merchant_repo.py::lock_for_update`, `backend/apps/payouts/repositories/merchant_repo.py::get_balance_breakdown`.
- Main callers: create-payout service, reconciliation, balance view, tests. Evidence: corresponding imports in `create_payout.py`, `reconcile_ledger.py`, `api/views.py`.
- Mutates what: nothing directly, but `lock_for_update()` affects concurrency control.
- Danger zones: every balance read is aggregate-based, so scale pressure lands here first.
- Debug here first when: available/held math is suspicious or concurrent create-payout races appear.

### `backend/apps/payouts/repositories/payout_repo.py`
- Purpose: create payout + hold, perform guarded state transitions, and claim stale rows with raw SQL. Evidence: `backend/apps/payouts/repositories/payout_repo.py::create_with_hold`, `backend/apps/payouts/repositories/payout_repo.py::transition`, `backend/apps/payouts/repositories/payout_repo.py::claim_stale_with_skip_locked`.
- Main callers: create-payout service, process-payout service, stale-retry service. Evidence: imports in those services.
- Mutates what: `Payout`, `PayoutEvent`, and indirectly `Transaction` via callbacks.
- Danger zones:
  - `transition()` uses conditional `update()` then appends event and invokes callback; failures inside callback run inside the surrounding transaction and roll back, but the ordering matters for reasoning
  - stale claim uses raw SQL, so schema drift or DB-specific assumptions surface here
  Evidence: `backend/apps/payouts/repositories/payout_repo.py::transition`, `backend/apps/payouts/repositories/payout_repo.py::claim_stale_with_skip_locked`.
- Debug here first when: status changes race, events are missing, or stale claim behavior differs across environments.

### `backend/apps/payouts/repositories/transaction_repo.py`
- Purpose: append transaction rows for credit, hold, release, and debit. Evidence: `backend/apps/payouts/repositories/transaction_repo.py`.
- Main callers: seed/tests, create-with-hold, process-payout, stale-retry. Evidence: imports across tests and services.
- Mutates what: `Transaction` table only.
- Danger zones: extremely thin wrappers, so any future metadata or audit enrichment must land here consistently or callers will fork behavior.
- Debug here first when: ledger rows are missing or wrong type.

### `backend/apps/payouts/repositories/idempotency_repo.py`
- Purpose: insert-or-get by key, persist replay payload, and purge expired idempotency rows. Evidence: `backend/apps/payouts/repositories/idempotency_repo.py`.
- Main callers: create-payout service and expiry task. Evidence: `backend/apps/payouts/services/create_payout.py`, `backend/apps/payouts/tasks/expire_idempotency.py`.
- Mutates what: `IdempotencyRecord`.
- Danger zones:
  - expired records for the same key are deleted before `get_or_create()`, which makes TTL semantically part of dedupe scope
  - `_status` is stored inside the JSON response body as an implementation detail
  Evidence: `backend/apps/payouts/repositories/idempotency_repo.py::insert_or_get_by_key`, `backend/apps/payouts/repositories/idempotency_repo.py::update_with_response`.
- Debug here first when: replay behavior, expiry, or key collisions look wrong.

### `backend/apps/payouts/repositories/event_repo.py`
- Purpose: append a payout event row. Evidence: `backend/apps/payouts/repositories/event_repo.py::append`.
- Main callers: `payout_repo.transition()`.
- Mutates what: `PayoutEvent`.
- Danger zones: intentionally tiny; if event payload needs enrichment, this file is the choke point.

## Domain Layer
### `backend/apps/payouts/domain/enums.py`
- Purpose: canonical status/type/state enum values shared across models and services.
- Debug here first when: a magic string mismatch causes constraint or transition errors.

### `backend/apps/payouts/domain/errors.py`
- Purpose: domain-level exception contracts translated by the API exception handler. Evidence: `backend/apps/payouts/domain/errors.py`, `backend/apps/payouts/api/exceptions.py::custom_exception_handler`.
- Debug here first when: HTTP error payloads drift from service intent.

### `backend/apps/payouts/domain/money.py`
- Purpose: money formatting, unit conversion, and canonical request hashing. Evidence: `backend/apps/payouts/domain/money.py::paise_to_rupees`, `backend/apps/payouts/domain/money.py::rupees_to_paise`, `backend/apps/payouts/domain/money.py::format_inr`, `backend/apps/payouts/domain/money.py::request_hash`.
- Danger zones: changing canonical JSON serialization in `request_hash()` would silently alter idempotency behavior.
- Debug here first when: duplicate requests are unexpectedly considered different.

### `backend/apps/payouts/domain/transitions.py`
- Purpose: hard gate legal payout lifecycle transitions. Evidence: `backend/apps/payouts/domain/transitions.py::LEGAL`, `backend/apps/payouts/domain/transitions.py::validate`.
- Debug here first when: a status update throws `InvalidStateTransition`.

## Async and Scheduler Files
### `backend/apps/payouts/tasks/payout_tasks.py`
- Purpose: Celery wrapper around `ProcessPayoutService`, preserving correlation ID. Evidence: `backend/apps/payouts/tasks/payout_tasks.py::process_payout`.
- Debug here first when: worker invocation works locally in service tests but not in real Celery runs.

### `backend/apps/payouts/tasks/sweep_stale.py`
- Purpose: beat-triggered stale recovery entrypoint. Evidence: `backend/apps/payouts/tasks/sweep_stale.py::sweep_stale`.
- Debug here first when: beat claims to run but stale payouts do not move.

### `backend/apps/payouts/tasks/expire_idempotency.py`
- Purpose: daily purge of expired idempotency records. Evidence: `backend/apps/payouts/tasks/expire_idempotency.py::expire_idempotency`.
- Debug here first when: old keys remain replayable longer than expected.

## Observability
### `backend/observability/*`
- `middleware.py`: binds and echoes `X-Correlation-Id`. Evidence: `backend/observability/middleware.py::CorrelationIdMiddleware`.
- `correlation.py`: context manager and accessor for trace propagation. Evidence: `backend/observability/correlation.py::bind_correlation_id`, `backend/observability/correlation.py::get_correlation_id`.
- `logging.py`: structlog JSON logger configuration. Evidence: `backend/observability/logging.py::configure_logging`.
- Debug here first when: logs lack correlation IDs or responses stop echoing tracing headers.

## Tests
### `backend/tests/*`
- Purpose: executable documentation for concurrency, API contracts, state machine legality, logging, reconciliation, stale retry, and DB constraints. Evidence: files under `backend/tests/integration` and `backend/tests/unit`.
- Highest-signal files:
  - payout contracts: `backend/tests/integration/test_payout_api_contracts.py`
  - concurrency: `backend/tests/integration/test_concurrency_tier1.py`, `backend/tests/integration/test_concurrency_tier2.py`
  - stale recovery: `backend/tests/integration/test_stale_sweeper.py`
  - state rules: `backend/tests/unit/test_domain_transitions.py`
  - drift detection: `backend/tests/integration/test_reconciliation.py`
- Debug here first when: you need to know intended behavior faster than reading the whole stack.

## Frontend Integration Surface
### `frontend/src/api/*`
- `client.ts`: shared fetch wrapper, merchant header injection, POST idempotency-key generation, and `ApiError` type. Evidence: `frontend/src/api/client.ts::fetchJson`, `frontend/src/api/client.ts::ApiError`.
- `merchantsApi.ts`: merchants, bank accounts, balance, and transactions calls. Evidence: `frontend/src/api/merchantsApi.ts`.
- `payoutsApi.ts`: create and list payout calls. Evidence: `frontend/src/api/payoutsApi.ts`.
- `types.ts`: frontend wire types. Evidence: `frontend/src/api/types.ts`.
- Debug here first when: backend works but browser requests/headers/body shapes do not.

### `frontend/src/hooks/*`
- `useMerchant.ts`: local-storage selection and merchant header propagation. Evidence: `frontend/src/hooks/useMerchant.ts::useMerchant`.
- `useBalance.ts`, `usePayouts.ts`: immediate fetch plus 3-second polling. Evidence: `frontend/src/hooks/useBalance.ts::useBalance`, `frontend/src/hooks/usePayouts.ts::usePayouts`, `frontend/src/hooks/usePolling.ts::usePolling`.
- `useTransactions.ts`: non-polling transactions fetch. Evidence: `frontend/src/hooks/useTransactions.ts::useTransactions`.
- `useCreatePayout.ts`: submit state and API-error translation. Evidence: `frontend/src/hooks/useCreatePayout.ts::useCreatePayout`.
- Debug here first when: the UI looks stale, keeps polling unexpectedly, or surfaces the wrong error text.

### `frontend/src/features/*`
- `MerchantSelector.tsx`: first load merchant list and current merchant chooser. Evidence: `frontend/src/features/MerchantSelector.tsx::MerchantSelector`.
- `DashboardPanel.tsx`: balance panel wrapper around `useBalance()`. Evidence: `frontend/src/features/DashboardPanel.tsx::DashboardPanel`.
- `PayoutForm.tsx`: amount parsing, bank account fetch, payout submission. Evidence: `frontend/src/features/PayoutForm.tsx::PayoutForm`.
- `PayoutHistorySection.tsx`: payout table and refetch callback exposure. Evidence: `frontend/src/features/PayoutHistorySection.tsx::PayoutHistorySection`.
- `TransactionLedger.tsx`: transaction table renderer. Evidence: `frontend/src/features/TransactionLedger.tsx::TransactionLedger`.
- Debug here first when: UI action wiring is wrong even though hooks and APIs seem fine.

## Runtime and Config Files
### `backend/config/settings/*`
- `base.py`: database config, DRF exception handler, Celery broker/result backend, beat schedule, CORS headers, and logging setup. Evidence: `backend/config/settings/base.py`.
- `dev.py`, `prod.py`, `test.py`: environment-specific overrides entrypoints. Evidence: files under `backend/config/settings/`.
- Debug here first when: behavior differs by environment, beat schedules vanish, or headers fail in browser requests.

### `docker-compose.yml`
- Purpose: runnable local topology with Postgres, Redis, web, worker, beat, and frontend services. Evidence: `docker-compose.yml`.
- Danger zones: `web` runs migrations and seed on startup every time, which is handy for demos but easy to forget during debugging. Evidence: `docker-compose.yml::web.command`.
- Debug here first when: "works on my machine" means "container wiring is wrong."

## Known Unknowns
- There is no explicit code-owner metadata in repo, so "ownership" here means behavioral ownership, not team assignment. Evidence: absence of CODEOWNERS file in explored paths. Confidence: High.
- The prompt names `config/settings/*`, but the actual repo path is `backend/config/settings/*`; this map follows runtime path, not prompt shorthand. Evidence: repo layout under `backend/config/settings/`. Confidence: High.
- Some frontend wire types are broader than individual backend responses, especially for `Payout`; that makes file ownership clear but contract exactness slightly fuzzier unless you check the corresponding endpoint. Evidence: `frontend/src/api/types.ts::Payout`, `backend/apps/payouts/api/serializers.py::PayoutResponseSerializer`, `backend/apps/payouts/services/create_payout.py::CreatePayoutService._run_critical_path`. Confidence: High.
