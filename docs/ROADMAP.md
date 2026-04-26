# Roadmap

Source spec: [`docs/plans/2026-04-25-playto-spec.md`](plans/2026-04-25-playto-spec.md). Phases below extract milestones from the spec — no new decisions live here.

## Phase 1 — Scaffold + Backend Layers + Core Models ✅
- ✅ Django 5 project scaffold; settings split (`base/dev/prod/test`); `psycopg3` driver
- ✅ Folder skeleton: `apps/payouts/{api,domain,repositories,services,tasks,management}`, `apps/merchants/`, `observability/`, `tests/{unit,integration}/`
- ✅ Domain modules: `enums.py`, `transitions.py` (LEGAL set + `validate()`), `errors.py`, `money.py`
- ✅ Models: `Merchant`, `BankAccount`, `Transaction` (4-type), `Payout`, `PayoutEvent`, `IdempotencyRecord`
- ✅ DB constraints: `CHECK` on amount, type enum, payout_id pairing; partial index on `payouts (status, last_attempted_at) WHERE status='processing'`
- ✅ pytest-django configured against real PostgreSQL (no sqlite); `--reuse-db` working
- ✅ Seed command (`manage.py seed`): 2–3 merchants, credits, bank accounts
- ✅ Unit tests: domain transitions, money helpers, request hash canonicalization

**Acceptance:** `manage.py migrate && manage.py seed` works; unit tests for `domain/*` pass; folder structure matches §13.1 of spec.

## Phase 2 — Ledger + Repositories + Balance APIs ✅
- ✅ `repositories/merchant_repo.py::lock_for_update()`, `get_balance_breakdown()` (single aggregation, no joins)
- ✅ `repositories/transaction_repo.py`: typed insert wrappers (`insert_credit`, `insert_hold`, `insert_release`, `insert_debit`)
- ✅ `services/dashboard.py::DashboardService`: bundles balance + recent transactions
- ✅ API: `GET /api/v1/merchants`, `GET /api/v1/merchants/{id}/balance`, `GET /api/v1/merchants/{id}/transactions`, `GET /api/v1/merchants/{id}/bank_accounts`
- ✅ DRF pagination on transactions list (LimitOffset, default 50)
- ✅ Integration test: `test_balance_aggregation` — all 4 txn types contribute correctly

**Acceptance:** balance APIs return correct values for seeded data; aggregation invariant test passes against real PG.

## Phase 3 — Payout Service + Locking + Idempotency ✅
- ✅ `repositories/idempotency_repo.py`: `insert_or_get_by_key()` with ON CONFLICT, `update_with_response()`, `purge_expired()`
- ✅ `repositories/payout_repo.py`: `create_with_hold()`, `transition()` (with `on_apply` callback)
- ✅ `repositories/event_repo.py`: `append()` (called from inside `transition()`)
- ✅ `services/create_payout.py::CreatePayoutService.execute()` — full 11-step orchestration with three-case idempotency and 422 error-path record update
- ✅ API: `POST /api/v1/payouts`, `GET /api/v1/payouts`, `GET /api/v1/payouts/{id}`, `GET /api/v1/payouts/{id}/events`
- ✅ DRF exception handler maps `InsufficientBalance→422`, `InvalidStateTransition→409`, `IdempotencyPayloadMismatch→409`, `BankAccountNotFound→404`
- ✅ Integration tests: `test_concurrency_tier1`, `test_concurrency_tier2`, `test_idempotency_replay`, `test_idempotency_in_flight`, `test_idempotency_payload_mismatch`, `test_state_machine_guards`

**Acceptance:** all six tests pass against real PG; `curl` reproduces idempotent replay byte-for-byte.

## Phase 4 — Worker Services + Retries + Stale Sweeper ✅
- ✅ Celery + Redis configured (broker + result backend); `acks_late=True`, `task_reject_on_worker_lost=True`
- ✅ Beat schedule wired (sweeper every 10s, idempotency expiry daily)
- ✅ `services/process_payout.py::ProcessPayoutService.execute()` — outcome simulation (70/20/10), atomic refund via `on_apply`
- ✅ `services/retry_stale.py::RetryStalePayoutsService.execute()` — `SELECT FOR UPDATE SKIP LOCKED` claim, inline retry (Option A — see spec §8), atomic max-attempts failure path
- ✅ `tasks/process_payout.py`, `tasks/sweep_stale.py`, `tasks/expire_idempotency.py` — thin `@shared_task` wrappers
- ✅ Correlation ID propagated from API request → Celery task header → task contextvars
- ✅ Integration tests: `test_worker_success`, `test_worker_failure_refund`, `test_worker_hang_retry_max`, `test_stale_sweeper`

**Acceptance:** worker test suite passes; manual hang scenario recovers within 30s; sweeper test asserts no double-claim under concurrent invocations.

## Phase 5 — Auditability + Reconciliation ✅
- ✅ `observability/logging.py`: structlog config, JSON renderer, contextvars for `correlation_id`/`payout_id`/`merchant_id`/`idempotency_key`/`attempt_number`
- ✅ `observability/middleware.py`: per-request correlation ID
- ✅ All log events from spec §15.2 emitted at correct call sites
- ✅ `services/reconcile_ledger.py::ReconcileLedgerService.execute()`: ledger ↔ payout invariants per spec §9
- ✅ `manage.py reconcile` command — exit 0 on clean, 1 on drift
- ✅ `manage.py stress_concurrency` harness (senior signal)
- ✅ Integration test: `test_reconciliation` — drift detection on injected row

**Acceptance:** `make reconcile` exits 0 on seeded data; `jq '.payout_id == "..."' logs.json` reconstructs full payout lifecycle from one trace.

## Phase 6 — Minimal Frontend (Layered) ✅
- ✅ Vite + React 18 + TS + Tailwind scaffold; ESLint+Prettier defaults (no Biome)
- ✅ `api/client.ts` — fetch wrapper, base URL from env, JSON parsing, error mapping, auto-injects `Idempotency-Key: crypto.randomUUID()` on POSTs unless caller passes one
- ✅ `api/payoutsApi.ts`, `api/merchantsApi.ts`, `api/types.ts`
- ✅ `utils/formatInr.ts` (Indian numbering ₹1,23,456.78), `utils/formatTimestamp.ts`, `utils/uuid.ts`, `utils/constants.ts`
- ✅ Hooks: `usePolling` (pauses on tab hidden), `useBalance`, `usePayouts`, `useTransactions`, `useCreatePayout`, `useMerchant` (localStorage)
- ✅ Presentational components: `BalanceCard`, `StatusBadge`, `MoneyText`, `PayoutRow`, `TransactionRow`, `TableShell`, `FormField`, `Button`
- ✅ Feature components: `MerchantSelector`, `DashboardPanel`, `PayoutForm`, `PayoutHistorySection`, `TransactionLedger`
- ✅ "Collected in USD · Paid out in INR" label visible on dashboard
- ✅ Polling at 3s; tab-hidden pauses; resumes on visible

**Acceptance:** dashboard shows seeded balance; payout submission updates list within 6s; tab-hidden pauses polling; idempotency-key auto-generated per submission.

## Phase 7 — Deploy + EXPLAINER ✅
- ✅ `docker-compose.yml`: postgres:16, redis:7, web (gunicorn), worker (celery), beat (celery beat), frontend (nginx-served Vite build)
- ✅ Single-command boot: `docker compose up -d --build` produces working seeded app
- ✅ Railway deployment: PG plugin, Redis plugin, services for web/worker/beat
- ✅ `Makefile` with targets per spec §16.4
- ✅ `README.md`: 5-line quickstart, architecture diagram, test instructions, deployed URL
- ✅ `EXPLAINER.md` — 9 sections per spec §17, all referencing real code paths
- ✅ `EXPLAIN ANALYZE` output for balance aggregation query and `SELECT FOR UPDATE` statement

**Acceptance:** fresh `docker compose up` boots seeded app + worker + beat + frontend in one command; deployed URL serves the same; EXPLAINER sections all verified against repo.

## Out of Scope
Authentication, customer payment ingestion, webhook delivery, event sourcing, WebSockets, multi-currency, pixel-perfect UI. See spec §18.
