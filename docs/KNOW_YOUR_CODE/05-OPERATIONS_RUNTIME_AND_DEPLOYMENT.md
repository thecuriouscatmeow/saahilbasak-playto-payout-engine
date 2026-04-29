# 05-OPERATIONS_RUNTIME_AND_DEPLOYMENT

## Runtime Topology
Local runtime is defined in Docker Compose with six services: `db`, `redis`, `web`, `worker`, `beat`, and `frontend`. Postgres and Redis have health checks; `web`, `worker`, and `beat` depend on them; `frontend` depends on `web`. Evidence: `docker-compose.yml`.

### Services
- `db`: `postgres:16-alpine` with `POSTGRES_DB=playto`, `POSTGRES_USER=postgres`, `POSTGRES_PASSWORD=playto`, and a named volume. Evidence: `docker-compose.yml::db`.
- `redis`: `redis:7-alpine` used as Celery broker and result backend. Evidence: `docker-compose.yml::redis`, `backend/config/settings/base.py::CELERY_BROKER_URL`, `backend/config/settings/base.py::CELERY_RESULT_BACKEND`.
- `web`: Django app container that runs migrations, seeds data, and starts Gunicorn with 3 workers on port 8000. Evidence: `docker-compose.yml::web`.
- `worker`: Celery worker with concurrency 2. Evidence: `docker-compose.yml::worker`.
- `beat`: Celery beat scheduler. Evidence: `docker-compose.yml::beat`.
- `frontend`: built from `./frontend`, exposed on port 5173 -> 80, with `API_HOST=web`. Evidence: `docker-compose.yml::frontend`, `frontend/Dockerfile`.

## Startup Order
Compose startup order is dependency-driven, not magical:
1. Postgres and Redis must become healthy.
2. `web` starts, runs `python manage.py migrate`, then `python manage.py seed`, then Gunicorn.
3. `worker` and `beat` start after DB and Redis are healthy.
4. `frontend` starts after `web`.
Evidence: `docker-compose.yml`.

The important operator implication is that `seed` is part of web startup, so local data is intentionally demo-friendly but not purely persistent-environment-neutral. Evidence: `docker-compose.yml::web.command`, `backend/tests/integration/test_seed.py`.

## Local Development Flow
Backend defaults point to local Postgres and Redis if env vars are absent, which means non-Compose local runs can still work if those services are available. Evidence: `backend/config/settings/base.py::DATABASES`, `backend/config/settings/base.py::CELERY_BROKER_URL`.

Frontend defaults to `http://localhost:8000` unless `VITE_API_BASE_URL` is set. Evidence: `frontend/src/api/client.ts::fetchJson`, `frontend/.env.example`.

The UI flow is:
1. load merchants
2. choose merchant
3. fetch and poll balance
4. fetch and poll payouts
5. fetch transactions
6. submit payout
Evidence: `frontend/src/App.tsx::App`, `frontend/src/features/MerchantSelector.tsx::MerchantSelector`, `frontend/src/features/DashboardPanel.tsx::DashboardPanel`, `frontend/src/features/PayoutForm.tsx::PayoutForm`, `frontend/src/features/PayoutHistorySection.tsx::PayoutHistorySection`, `frontend/src/features/TransactionLedger.tsx::TransactionLedger`.

## Environment Variables
### Backend
- `DATABASE_URL`: parsed into Django `DATABASES`. Evidence: `backend/config/settings/base.py::DATABASES`.
- `REDIS_URL`: powers both Celery broker and result backend. Evidence: `backend/config/settings/base.py::CELERY_BROKER_URL`, `backend/config/settings/base.py::CELERY_RESULT_BACKEND`.
- `DJANGO_SECRET_KEY`: secret key input. Evidence: `backend/config/settings/base.py::SECRET_KEY`.
- `DJANGO_DEBUG`: toggles debug mode. Evidence: `backend/config/settings/base.py::DEBUG`.
- `ALLOWED_HOSTS`: comma-separated host list. Evidence: `backend/config/settings/base.py::ALLOWED_HOSTS`.
- `CORS_ALLOWED_ORIGINS`: comma-separated browser origins. Evidence: `backend/config/settings/base.py::CORS_ALLOWED_ORIGINS`.

### Frontend
- `VITE_API_BASE_URL`: browser API base URL. Evidence: `frontend/src/api/client.ts::fetchJson`, `frontend/.env.example`.

## Redis and Celery Usage
Redis here acts like caffeinated courier pigeons for Celery: it carries task messages and result backend state, not business truth. Business truth remains in Postgres tables. Evidence: `backend/config/settings/base.py::CELERY_BROKER_URL`, `backend/config/settings/base.py::CELERY_RESULT_BACKEND`, `backend/apps/payouts/models.py`.

Celery workload in this repo includes:
- payout processing task
- stale sweep task
- idempotency expiry task
Evidence: `backend/apps/payouts/tasks/payout_tasks.py::process_payout`, `backend/apps/payouts/tasks/sweep_stale.py::sweep_stale`, `backend/apps/payouts/tasks/expire_idempotency.py::expire_idempotency`.

Beat schedule:
- `sweep-stale`: every 10 seconds
- `expire-idempotency`: daily at 03:00
Evidence: `backend/config/settings/base.py::CELERY_BEAT_SCHEDULE`, `backend/tests/integration/test_celery_config.py`.

## Logging and Correlation IDs
Structlog is configured to emit JSON with merged contextvars, log level, timestamp, and rendered event objects. Evidence: `backend/observability/logging.py::configure_logging`.

Request middleware binds `X-Correlation-Id` if supplied or generates a UUID, then echoes it in the response. Evidence: `backend/observability/middleware.py::CorrelationIdMiddleware`, `backend/tests/integration/test_correlation_middleware.py`.

Worker tasks bind a correlation ID from the enqueue call or fallback task request ID. Evidence: `backend/apps/payouts/tasks/payout_tasks.py::process_payout`, `backend/observability/correlation.py::bind_correlation_id`.

Important log evidence includes `payout.created` on successful create-path completion and `payout.funds_released` on release insertion. Evidence: `backend/apps/payouts/services/create_payout.py::CreatePayoutService.execute`, `backend/apps/payouts/repositories/transaction_repo.py::insert_release`, `backend/tests/integration/test_log_events.py::test_payout_created_log_emitted`.

## Common Local Failures
- DB or Redis not healthy, which blocks `web`, `worker`, and `beat`. Evidence: `docker-compose.yml`.
- `web` container fails during `migrate` or `seed`, so API never starts. Evidence: `docker-compose.yml::web.command`.
- Browser cannot reach backend because `VITE_API_BASE_URL` is wrong in non-Compose local dev. Evidence: `frontend/src/api/client.ts::fetchJson`.
- CORS errors if frontend origin is not present in `CORS_ALLOWED_ORIGINS`. Evidence: `backend/config/settings/base.py::CORS_ALLOWED_ORIGINS`.
- Stale payouts never recover if beat is down, even while API and worker are healthy. Evidence: `backend/config/settings/base.py::CELERY_BEAT_SCHEDULE`, `backend/apps/payouts/tasks/sweep_stale.py::sweep_stale`.
- Merchant selection/header propagation broken in frontend, so payout list/detail scoping appears empty. Evidence: `frontend/src/hooks/useMerchant.ts::useMerchant`, `frontend/src/api/client.ts::fetchJson`.

## If Nothing Works, Check These 7 Things First
1. Is Postgres healthy and accepting connections from `DATABASE_URL`? Evidence: `docker-compose.yml::db`, `backend/config/settings/base.py::DATABASES`.
2. Is Redis healthy and reachable by both `worker` and `beat`? Evidence: `docker-compose.yml::redis`, `backend/config/settings/base.py::CELERY_BROKER_URL`.
3. Did `web` finish `migrate` and `seed` before Gunicorn start? Evidence: `docker-compose.yml::web.command`.
4. Is Celery worker running and consuming `payouts.process_payout` tasks? Evidence: `docker-compose.yml::worker`, `backend/apps/payouts/tasks/payout_tasks.py::process_payout`.
5. Is beat running so stale sweep and idempotency expiry still happen? Evidence: `docker-compose.yml::beat`, `backend/config/settings/base.py::CELERY_BEAT_SCHEDULE`.
6. Is the browser calling the right API base URL and allowed CORS origin? Evidence: `frontend/src/api/client.ts::fetchJson`, `backend/config/settings/base.py::CORS_ALLOWED_ORIGINS`.
7. Are correlation IDs and JSON logs visible so you can trace one request across API and worker? Evidence: `backend/observability/middleware.py::CorrelationIdMiddleware`, `backend/observability/logging.py::configure_logging`, `backend/apps/payouts/tasks/payout_tasks.py::process_payout`.

## Production-Leaning Concerns Visible From Repo
- `CELERY_TASK_ACKS_LATE=True` and `CELERY_TASK_REJECT_ON_WORKER_LOST=True` indicate the system prefers redelivery after worker loss over silent task disappearance. Evidence: `backend/config/settings/base.py::CELERY_TASK_ACKS_LATE`, `backend/config/settings/base.py::CELERY_TASK_REJECT_ON_WORKER_LOST`, `backend/tests/integration/test_celery_config.py::test_task_acks_late`.
- `CELERY_TASK_TIME_LIMIT=30` bounds task runtime. Evidence: `backend/config/settings/base.py::CELERY_TASK_TIME_LIMIT`.
- Gunicorn worker count is hardcoded to 3 in Compose, not auto-derived. Evidence: `docker-compose.yml::web.command`.

## Known Unknowns
- There is no infrastructure-as-code or deployment manifest beyond Docker Compose, so actual production orchestration, secret injection, autoscaling, and backup strategy are not proven by repo state. Evidence: explored root files include `docker-compose.yml` but no Terraform/Kubernetes manifests. Confidence: High.
- `prod.py` exists, but this documentation pass did not find a runtime deployment definition showing exactly which settings module is used in Railway or other production environments. Evidence: `backend/config/settings/prod.py`, absence of deploy manifest in explored files. Confidence: Medium.
- `seed` behavior is part of local startup, but the command implementation was not inspected in this pass; assumptions about idempotence or destructive reseeding should be verified before relying on it in repeatable environments. Evidence: `docker-compose.yml::web.command`, `backend/tests/integration/test_seed.py`. Confidence: Medium.
