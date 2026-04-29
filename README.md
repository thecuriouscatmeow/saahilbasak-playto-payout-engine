# Playto Payout Engine

## What this is

A cross-border merchant payout engine built as a Founding Engineer challenge. Merchants collect payments in USD and receive payouts in INR via a ledger-based system with strong consistency guarantees.

Graded on: ledger correctness under concurrency, idempotency rigor, atomic state transitions, worker failure realism, and observability depth.

## Quickstart

```bash
git clone https://github.com/thecuriouscatmeow/saahilbasak-playto-payout-engine.git
cd saahilbasak-playto-payout-engine
docker compose up --build
# open http://localhost:5173
```

> Requires Docker. `docker compose up` starts postgres, redis, bank simulator, django, celery worker, celery beat, and the React dashboard in one command.

**Manual startup (two terminals):**
```bash
# Terminal 1 — payout engine
cd backend && source .venv/bin/activate
DATABASE_URL=postgresql://postgres:playto@localhost:5432/playto python manage.py migrate
DATABASE_URL=postgresql://postgres:playto@localhost:5432/playto python manage.py seed
DATABASE_URL=postgresql://postgres:playto@localhost:5432/playto python manage.py runserver

# Terminal 2 — bank simulator
cd bank_simulator && pip install -r requirements.txt
ENGINE_WEBHOOK_URL=http://localhost:8000/api/v1/webhooks/bank-callback uvicorn app:app --port 8001 --reload
```

**Sample curl flow:**
```bash
# Create a payout (replace IDs from seed output)
curl -X POST http://localhost:8000/api/v1/payouts/ \
  -H "Content-Type: application/json" \
  -H "X-Merchant-Id: <merchant_id>" \
  -H "Idempotency-Key: test-1" \
  -d '{"amount_paise": 5000, "bank_account_id": "<bank_account_id>"}'

# Poll status (~500ms later — webhook drives completion)
curl http://localhost:8000/api/v1/payouts/<payout_id>/
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  React Dashboard (Vite + TS + Tailwind) — port 5173     │
│  api/ · hooks/ · components/ · features/ · utils/      │
└────────────────────┬────────────────────────────────────┘
                     │ HTTP /api/v1/
┌────────────────────▼────────────────────────────────────┐
│  Django 6 + DRF — port 8000                             │
│  API layer → Services → Repositories → Domain           │
└──────┬──────────────────────────┬────────────┬──────────┘
       │ SQL (psycopg3)            │ Celery tasks│ webhooks
┌──────▼──────┐    ┌──────────────▼──┐    ┌────▼────────────────┐
│ PostgreSQL  │    │ Redis (broker)  │    │ Bank Simulator      │
│ 16-alpine   │    │ worker + beat   │    │ FastAPI — port 8001 │
└─────────────┘    └─────────────────┘    └─────────────────────┘
```

Four backend layers:
- **API** (`apps/*/api/`) — DRF views, serializers, custom exception handler mapping domain errors to HTTP status codes
- **Services** (`apps/payouts/services/`) — orchestration: `CreatePayoutService`, `ProcessPayoutService`, `RetryStalePayoutsService`, `ReconcileLedgerService`
- **Repositories** (`apps/payouts/repositories/`) — all DB access: `merchant_repo`, `payout_repo`, `transaction_repo`, `idempotency_repo`, `event_repo`
- **Domain** (`apps/payouts/domain/`) — pure Python: enums, state machine transitions, error types, money helpers

Five frontend zones: `api/` (typed fetch), `hooks/` (data + polling), `components/` (pure presentational), `features/` (composed UI panels), `utils/` (formatInr, timestamps, constants).

## Tests

```bash
make test          # full pytest suite (87 tests) inside Docker
make stress        # stress_concurrency: 3 merchants × 10 workers × 5s
make reconcile     # ledger ↔ payout invariant check
```

Or run locally:
```bash
cd backend
source .venv/bin/activate
DATABASE_URL=postgresql://postgres:playto@localhost:5432/playto pytest -v
```

## Deployed URL

- **Frontend:** https://frontend-production-a3db.up.railway.app
- **API:** https://web-production-15d76.up.railway.app

## Where to read first

- `EXPLAINER.md` — design rationale for every hard decision (locking, idempotency, state machine, sweeper, observability)
- `backend/apps/payouts/services/create_payout.py` — the critical path: lock → balance check → hold → idempotency
- `backend/apps/payouts/repositories/payout_repo.py` — `transition()`: WHERE-clause guard + `on_apply` callback
- `backend/apps/payouts/repositories/merchant_repo.py` — the single-aggregation balance query
- `docs/plans/2026-04-25-playto-spec.md` — frozen architecture spec
