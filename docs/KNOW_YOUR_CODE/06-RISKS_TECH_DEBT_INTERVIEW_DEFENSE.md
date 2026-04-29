# 06-RISKS_TECH_DEBT_INTERVIEW_DEFENSE

## Risk Prioritization
Issues are sorted highest impact first and ranked with Severity, Likelihood, Blast Radius, Fix Effort, and Recommended Fix, per the plan.

### 1. Synchronous `time.sleep()` polling in payout create path
- Why it matters: duplicate in-flight idempotent requests block a request thread for up to 1 second total, which is exactly the path most likely to be exercised during retries, flaky networks, or impatient clients. Evidence: `backend/apps/payouts/services/create_payout.py::CreatePayoutService._handle_existing_record`, `backend/tests/integration/test_idempotency_in_flight.py::test_in_flight_second_request_returns_202_or_stored`.
- Severity: High
- Likelihood: Medium
- Blast Radius: API latency, worker pool utilization, tail-response time under load
- Fix Effort: Medium
- Recommended Fix: replace sleep-loop polling with immediate `202` return plus client-visible retry contract, or move replay completion signaling to a non-blocking cache/outbox mechanism.

### 2. Post-commit queue enqueue without outbox protection
- Why it matters: the payout and hold commit before `process_payout.apply_async()` runs, so broker failure in that window can strand money in `pending` with held funds and no worker pickup. Evidence: `backend/apps/payouts/services/create_payout.py::CreatePayoutService._run_critical_path`.
- Severity: High
- Likelihood: Medium
- Blast Radius: stuck funds, manual ops intervention, mismatch between HTTP success and async execution
- Fix Effort: High
- Recommended Fix: introduce a transactional outbox or a durable "needs_dispatch" state with a dispatcher job.

### 3. Aggregate balance computation on every read and create
- Why it matters: available balance is recomputed by aggregating the full transaction ledger each time, both for read endpoints and pre-payout reservation checks. This is clean for correctness but expensive as ledger size grows. Evidence: `backend/apps/payouts/repositories/merchant_repo.py::get_balance_breakdown`, `backend/apps/payouts/services/create_payout.py::CreatePayoutService._run_critical_path`, `backend/apps/payouts/api/views.py::BalanceView`.
- Severity: High
- Likelihood: High
- Blast Radius: payout create latency, balance page latency, DB CPU
- Fix Effort: High
- Recommended Fix: add a materialized balance snapshot or merchant balance table updated transactionally, while preserving reconciliation against the ledger.

### 4. Lock contention on merchant row during payout creation
- Why it matters: `select_for_update()` serializes all payout creation per merchant, which prevents double spending but creates hot-row contention for active merchants. Evidence: `backend/apps/payouts/repositories/merchant_repo.py::lock_for_update`, `backend/tests/integration/test_concurrency_tier2.py::test_concurrency_tier2`.
- Severity: High
- Likelihood: Medium
- Blast Radius: throughput ceilings for high-volume merchants
- Fix Effort: Medium
- Recommended Fix: keep the lock for v1 correctness, but consider per-merchant balance snapshots, advisory locks, or more granular reservation models in v2.

### 5. Stale retry path partially bypasses repository transition abstraction
- Why it matters: stale retry increments `attempts` and `last_attempted_at` with direct ORM `update()` before terminal transition logic runs, so audit/event behavior is not fully centralized. Evidence: `backend/apps/payouts/services/retry_stale.py::RetryStalePayoutsService._handle_stale`.
- Severity: Medium
- Likelihood: High
- Blast Radius: inconsistent observability, harder reasoning about lifecycle history
- Fix Effort: Low
- Recommended Fix: route attempt-bump behavior through a repository helper that also emits an event or structured log.

### 6. Hardcoded retry and TTL knobs in application code
- Why it matters: idempotency TTL is 24 hours, stale max attempts is 3, sweep threshold defaults to 30 seconds, and SQL claim limit defaults to 100. These are operational knobs disguised as constants. Evidence: `backend/apps/payouts/services/create_payout.py::CreatePayoutService.IDEMPOTENCY_TTL_HOURS`, `backend/apps/payouts/services/retry_stale.py::MAX_ATTEMPTS`, `backend/apps/payouts/services/retry_stale.py::RetryStalePayoutsService.__init__`, `backend/apps/payouts/repositories/payout_repo.py::claim_stale_with_skip_locked`.
- Severity: Medium
- Likelihood: High
- Blast Radius: stale recovery behavior, dedupe policy, queue pressure
- Fix Effort: Low
- Recommended Fix: move them to settings with sane defaults and expose them in ops docs.

### 7. Worker duplicate-processing safety depends on conditional status update, not stronger task idempotency
- Why it matters: this is a valid pattern, but all correctness hangs on `transition(... where status=frm)` working exactly as intended and every terminal mutation going through that path. Evidence: `backend/apps/payouts/repositories/payout_repo.py::transition`, `backend/apps/payouts/services/process_payout.py::ProcessPayoutService.execute`, `backend/tests/integration/test_worker_success.py::test_already_handled_is_noop`.
- Severity: Medium
- Likelihood: Medium
- Blast Radius: payout terminal-state duplication if future code bypasses repository guards
- Fix Effort: Medium
- Recommended Fix: preserve the repository gate as the only terminal-mutation path and add regression tests whenever worker logic changes.

### 8. Sparse metrics and dashboards
- Why it matters: the repo has correlation IDs and JSON logs, but no counters, histograms, alert thresholds, or exposed reconciliation/sweeper health metrics. Logs help during incidents; metrics help you discover the incident exists. Evidence: `backend/observability/logging.py::configure_logging`, `backend/observability/middleware.py::CorrelationIdMiddleware`, absence of metrics library usage in explored code.
- Severity: Medium
- Likelihood: High
- Blast Radius: slower detection of stuck payouts, sweep failures, or latency regressions
- Fix Effort: Medium
- Recommended Fix: add metrics for create latency, payout age by status, stale sweeps, retries, terminal outcomes, and idempotency replay rates.

### 9. Frontend and backend payout response shapes are not perfectly aligned
- Why it matters: frontend `Payout` type expects `updated_at`, but create response omits it and read serializer shape is also not fully identical to the type. This may not break current UI usage, but it is a contract-paper-cut waiting to grow teeth. Evidence: `frontend/src/api/types.ts::Payout`, `backend/apps/payouts/services/create_payout.py::CreatePayoutService._run_critical_path`, `backend/apps/payouts/api/serializers.py::PayoutResponseSerializer`.
- Severity: Low
- Likelihood: Medium
- Blast Radius: frontend type drift, future UI regressions
- Fix Effort: Low
- Recommended Fix: define endpoint-specific TypeScript types or normalize backend response shapes.

## Interview Defense
### Why choose a ledger?
A ledger is defendable because it gives you reconstructable financial truth, supports reconciliation, and avoids "some code forgot to update balance" failure modes. In this repo, every meaningful balance answer comes from transactions, and reconciliation explicitly checks payout-state-to-ledger consistency. Evidence: `backend/apps/payouts/repositories/merchant_repo.py::get_balance_breakdown`, `backend/apps/payouts/services/reconcile_ledger.py::ReconcileLedgerService`.

### Why choose DB locks?
The row lock is the nightclub bouncer preventing double spending. For v1 money movement, serializing reservations per merchant is a reasonable tradeoff: simpler correctness now, throughput tuning later. Evidence: `backend/apps/payouts/repositories/merchant_repo.py::lock_for_update`, `backend/tests/integration/test_concurrency_tier1.py::test_concurrency_tier1`, `backend/tests/integration/test_concurrency_tier2.py::test_concurrency_tier2`.

### Why idempotency via DB constraint?
Database uniqueness on `(merchant, idempotency_key)` is harder to bypass than in-memory request caches and survives process restarts. The stored `request_hash` then distinguishes honest retries from key misuse. Evidence: `backend/apps/payouts/models.py::IdempotencyRecord.Meta`, `backend/apps/payouts/repositories/idempotency_repo.py::insert_or_get_by_key`, `backend/apps/payouts/services/create_payout.py::CreatePayoutService._handle_existing_record`.

### Honest tradeoffs to admit
- The system is correctness-first, not throughput-first. Evidence: `select_for_update()` and aggregate balance reads.
- Settlement is simulated, so integration complexity is deferred, not solved. Evidence: `backend/apps/payouts/services/process_payout.py::simulate_bank_settlement`.
- Recovery exists, but observability is still more log-driven than metrics-driven. Evidence: `backend/observability/logging.py::configure_logging`, no metrics layer found.

### What to improve in v2
- transactional outbox for worker dispatch
- materialized merchant balance snapshots with reconciliation
- settings-driven retry/TTL knobs
- real bank integration abstraction
- metrics/alerts and operator dashboards
Evidence: risks above and corresponding code anchors.

## 30-Minute New Engineer Reading Order
1. `backend/apps/payouts/services/create_payout.py::CreatePayoutService`
2. `backend/apps/payouts/repositories/merchant_repo.py::get_balance_breakdown`
3. `backend/apps/payouts/repositories/payout_repo.py::transition`
4. `backend/apps/payouts/services/process_payout.py::ProcessPayoutService`
5. `backend/apps/payouts/services/retry_stale.py::RetryStalePayoutsService`
6. `backend/tests/integration/test_payout_api_contracts.py`
7. `backend/tests/integration/test_concurrency_tier2.py`
8. `frontend/src/App.tsx::App` plus `frontend/src/api/client.ts::fetchJson`

## Production Incident Debug Playbook
1. Find the `payout_id`, `merchant_id`, and `X-Correlation-Id` from API logs. Evidence: `backend/tests/integration/test_log_events.py::test_payout_created_log_emitted`, `backend/observability/middleware.py::CorrelationIdMiddleware`.
2. Inspect payout status, attempts, and `last_attempted_at` in `payouts`. Evidence: `backend/apps/payouts/models.py::Payout`.
3. Inspect related `transactions` and `payout_events` for hold/debit/release shape. Evidence: `backend/apps/payouts/models.py::Transaction`, `backend/apps/payouts/models.py::PayoutEvent`.
4. If status is `pending`, verify worker dispatch and queue health. Evidence: `backend/apps/payouts/tasks/payout_tasks.py::process_payout`, `backend/config/settings/base.py::CELERY_BROKER_URL`.
5. If status is `processing`, verify beat and stale sweep are running. Evidence: `backend/apps/payouts/tasks/sweep_stale.py::sweep_stale`, `backend/config/settings/base.py::CELERY_BEAT_SCHEDULE`.
6. Recompute ledger expectations with `ReconcileLedgerService` logic to check for drift. Evidence: `backend/apps/payouts/services/reconcile_ledger.py::ReconcileLedgerService`.
7. If duplicate client requests are involved, inspect `idempotency_records` for `request_hash`, `state`, and stored response. Evidence: `backend/apps/payouts/models.py::IdempotencyRecord`, `backend/apps/payouts/repositories/idempotency_repo.py`.

## If Interview Is Tomorrow, Read These Files First
1. `backend/apps/payouts/services/create_payout.py`
2. `backend/apps/payouts/repositories/merchant_repo.py`
3. `backend/apps/payouts/repositories/payout_repo.py`
4. `backend/apps/payouts/services/process_payout.py`
5. `backend/apps/payouts/services/retry_stale.py`
6. `backend/tests/integration/test_concurrency_tier1.py`
7. `backend/tests/integration/test_stale_sweeper.py`
8. `frontend/src/api/client.ts`

## 10 Questions A Senior Interviewer Will Ask About This Codebase
1. Why derive balance from transactions instead of storing a balance field?
2. What prevents double spending under concurrent payout creation?
3. Why use a DB uniqueness constraint for idempotency instead of Redis?
4. What happens if the DB commit succeeds but Celery enqueue fails?
5. Why is stale recovery on a scheduler instead of immediate worker retry?
6. How do you prove terminal payouts have correct ledger offsets?
7. What scale bottleneck shows up first for a merchant with millions of transactions?
8. How do you trace one payout across API and worker boundaries?
9. What parts of this design are demo scaffolding versus production-ready?
10. What would you change before connecting to a real bank rail?

## Documentation Drift Risks
- Routes can change without doc updates because URL wiring is split across `backend/config/urls.py`, `backend/apps/merchants/api/urls.py`, and `backend/apps/payouts/api/payout_urls.py`. Recommended CI guard: compare documented route inventory against Django URL introspection or a generated route snapshot.
- Schema or constraint changes can drift from docs if models or migrations change without corresponding ledger/schema notes. Recommended CI guard: fail docs checks when `backend/apps/*/models.py` or `migrations/*.py` change without touching `docs/KNOW_YOUR_CODE/`.
- Celery schedules can drift from ops docs if `CELERY_BEAT_SCHEDULE` changes silently. Recommended CI guard: snapshot schedule keys and cadence from `backend/config/settings/base.py`.
- Frontend hook behavior can drift from flow docs if polling cadence or merchant-header injection changes. Recommended CI guard: require docs touch when `frontend/src/hooks/*` or `frontend/src/api/client.ts` changes.
- Risk rankings can go stale when architecture changes. Recommended CI guard: add a lightweight review checklist in PR template asking whether `06-RISKS_TECH_DEBT_INTERVIEW_DEFENSE.md` still reflects current behavior.

## Known Unknowns
- Severity ordering is based on repo-visible architecture and tests, not production incident history or traffic data. Evidence: no telemetry dashboards or incident archive found in explored files. Confidence: Medium.
- Some risks may be intentionally accepted for interview/demo scope rather than accidental omissions, especially simulated bank settlement and minimal auth. Evidence: `backend/apps/payouts/services/process_payout.py::simulate_bank_settlement`, absence of auth layer in `backend/config/settings/base.py`. Confidence: Medium.
- No direct test was found for enqueue failure after DB commit, so that risk is architecture-derived rather than test-demonstrated. Evidence: `backend/apps/payouts/services/create_payout.py::CreatePayoutService._run_critical_path`. Confidence: Medium.
