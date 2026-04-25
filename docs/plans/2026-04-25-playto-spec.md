# Spec — Playto Payout Engine

| | |
|---|---|
| **Date** | 2026-04-25 |
| **Status** | Pending approval |
| **Owner** | thecuriousbox |
| **Source SRS** | `docs/SRS.md` |
| **Source REQ** | `docs/REQUIREMENTS.md` |
| **Supersedes** | — |
| **Frozen on approval** | Architecture, layers, data model, critical paths, API contracts, test strategy |

> This spec is the source of truth for implementation. Subplans extract milestones from it. Implementation deviations from this spec require an updated spec entry, not silent drift.

---

## 1. Goal

Build a merchant payout engine that holds USD float and settles INR to Indian bank accounts, demonstrating ledger correctness, concurrency safety, idempotency rigor, atomic state transitions, and worker failure realism. CTO grades correctness and judgment, not features or UI.

### Code Quality Constraints (apply everywhere)

This is an interview submission. Every committed file should earn its place. The reviewer is a CTO grading judgment and signal-to-noise.

- **No dead code.** Unused functions, commented-out blocks, "for later" stubs → delete before commit.
- **No exploratory scripts.** One-time-use debug/probe scripts created during development must be deleted, not parked in `scripts/` for posterity.
- **Lean comments.** Default to none. Only comment when the *why* is non-obvious — a hidden invariant, a subtle constraint, a workaround for a specific bug. Never narrate what readable code already says.
- **No DocOps/AI-tooling artifacts in tree.** `CLAUDE.md`, `.claude/`, AI config, agent settings — all gitignored. Not part of the submission.
- **Verification rule for every milestone:** before commit, scan diff for dead code, leftover scripts, narration comments. If found → cut.

### Acceptance Criteria (whole effort)

1. **Concurrency**: Tier-1 (₹100, two ₹60) and Tier-2 (₹300, ten ₹60) tests pass against real PostgreSQL.
2. **Idempotency**: replay, payload-mismatch (409), and in-flight (202) tests pass.
3. **State machine**: every transition tested; illegal transitions raise `InvalidStateTransition`.
4. **Worker lifecycle**: success, failure-with-refund, hang→retry→max-attempts paths all tested.
5. **Atomic refund**: failure path test asserts state flip and `release` insert commit together.
6. **Stale recovery**: sweeper claims under concurrency without double-claim; max-attempts path tested.
7. **Reconciliation**: `manage.py reconcile` exits 0 on seeded data; documented invariant.
8. **One-command boot**: `docker compose up` yields seeded app + worker + beat + frontend.
9. **EXPLAINER.md** sections all reference real code paths in the repo.

---

## 2. Tech Stack (frozen)

| Layer | Choice |
|---|---|
| Backend | Django 5 + DRF |
| DB | PostgreSQL 16 |
| DB driver | psycopg3 (`psycopg[binary]`) |
| Background jobs | Celery + Redis (broker + result backend) |
| Logging | structlog (JSON renderer, contextvars) |
| Test runner | pytest + pytest-django (real PG, no sqlite) |
| Frontend | Vite + React 18 + TypeScript + Tailwind |
| Frontend polling | Plain `setInterval` via `usePolling` hook |
| Container orchestration | docker-compose |
| Deploy target | Railway |

Out of scope: TanStack Query, shadcn/ui, Biome, uv, mypy strict, Django Channels/WebSockets, Next.js, microservices.

---

## 3. Architectural Layers

### 3.1 Backend (4 layers)

| Layer | Owns | Forbidden |
|---|---|---|
| **API** | DRF views, serializers, request validation, error→HTTP mapping, URL routing | DB writes, business rules |
| **Services** | Orchestration: atomic blocks, lock acquisition, repo calls in correct order, task dispatch, raising domain errors | Direct ORM `.objects` access (goes via repos), HTTP concerns |
| **Repositories** | All ORM queries: `select_for_update`, balance aggregation, conditional UPDATEs, `ON CONFLICT`, `SKIP LOCKED` claims | Business rules, multi-step orchestration, raising domain errors |
| **Domain** | Enums, transition table, money helpers, exception types | Any I/O |

Tasks are **thin wrappers**: `@shared_task` decorator + one call into a service. Services are unit-testable without a worker.

### 3.2 Frontend (5 zones)

| Zone | Owns | Forbidden |
|---|---|---|
| **API client** | fetch wrapper, base URL, idempotency-key injection, error parsing | UI, business rules |
| **Hooks** | data fetching, polling, mutations, derived state, idempotency-key generation | JSX |
| **Presentational components** | pure UI from props | `fetch`, `useEffect` for data |
| **Feature components** | compose presentational + hooks for one slice | direct API calls (use hooks) |
| **Utils** | pure functions: INR formatting, timestamps, UUID | I/O |

---

## 4. Data Model

All amounts stored as `BigIntegerField` in **paise**. No `FloatField`. No `DecimalField`.

### 4.1 Tables

#### `merchants`
| field | type | notes |
|---|---|---|
| id | UUID PK | |
| name | text NOT NULL | |
| created_at | timestamptz NOT NULL DEFAULT now() | |

#### `bank_accounts`
| field | type | notes |
|---|---|---|
| id | UUID PK | |
| merchant_id | UUID FK→merchants ON DELETE CASCADE NOT NULL | indexed |
| account_number | text NOT NULL | |
| ifsc | text NOT NULL | |
| label | text NOT NULL | e.g. "Primary HDFC" |
| created_at | timestamptz NOT NULL DEFAULT now() | |

#### `transactions` (the ledger — append-only)
| field | type | notes |
|---|---|---|
| id | UUID PK | |
| merchant_id | UUID FK→merchants NOT NULL | |
| type | text NOT NULL | enum: `credit` \| `hold` \| `release` \| `debit` |
| amount_paise | BIGINT NOT NULL | `CHECK (amount_paise > 0)` |
| payout_id | UUID FK→payouts NULL | |
| reference | text NULL | optional human-readable note |
| created_at | timestamptz NOT NULL DEFAULT now() | |

Constraints:
- `CHECK (type IN ('credit','hold','release','debit'))`
- `CHECK ((type = 'credit') = (payout_id IS NULL))` — only credits are payout-less; the other three always reference a payout
- Index `(merchant_id, created_at DESC)` — ledger views, balance aggregation
- Index `(payout_id)` — payout-scoped lookups

The ledger is **append-only**. No UPDATE, no DELETE in application code. Migrations and admin tooling are the only exception.

#### `payouts`
| field | type | notes |
|---|---|---|
| id | UUID PK | |
| merchant_id | UUID FK→merchants NOT NULL | |
| bank_account_id | UUID FK→bank_accounts NOT NULL | |
| amount_paise | BIGINT NOT NULL | `CHECK (amount_paise > 0)` |
| status | text NOT NULL | enum: `pending` \| `processing` \| `completed` \| `failed` |
| attempt_count | int NOT NULL DEFAULT 0 | incremented on each `pending→processing` |
| last_attempted_at | timestamptz NULL | |
| idempotency_key | UUID NOT NULL | for traceability/logs |
| created_at | timestamptz NOT NULL DEFAULT now() | |
| updated_at | timestamptz NOT NULL DEFAULT now() | |

Constraints:
- `CHECK (status IN ('pending','processing','completed','failed'))`
- Index `(merchant_id, created_at DESC)` — payout lists
- Partial index `(status, last_attempted_at) WHERE status = 'processing'` — sweeper query

#### `payout_events` (audit log)
| field | type | notes |
|---|---|---|
| id | UUID PK | |
| payout_id | UUID FK→payouts NOT NULL | indexed |
| from_status | text NULL | NULL only for the synthetic "created" event |
| to_status | text NOT NULL | |
| attempt | int NOT NULL | snapshot of `attempt_count` at transition |
| reason | text NULL | e.g. "bank_settlement_failed", "max_attempts_exceeded" |
| created_at | timestamptz NOT NULL DEFAULT now() | |

Index `(payout_id, created_at)` — chronological reconstruction.

#### `idempotency_records`
| field | type | notes |
|---|---|---|
| id | UUID PK | |
| merchant_id | UUID FK→merchants NOT NULL | |
| idempotency_key | UUID NOT NULL | merchant-scoped |
| request_hash | text NOT NULL | sha256 hex of canonical-json(body) |
| state | text NOT NULL | enum: `in_progress` \| `completed` |
| payout_id | UUID FK→payouts NULL | populated after first request commits |
| response_status_code | int NULL | populated after first request commits |
| response_body | jsonb NULL | populated after first request commits |
| created_at | timestamptz NOT NULL DEFAULT now() | |
| expires_at | timestamptz NOT NULL | `created_at + 24h` |

Constraints:
- `CHECK (state IN ('in_progress','completed'))`
- `UNIQUE (merchant_id, idempotency_key)` — the concurrency primitive for idempotency
- Index `(expires_at)` — purge sweeper

### 4.2 Enums (single source of truth in `apps/payouts/domain/enums.py`)

```python
class PayoutStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class TxnType(str, Enum):
    CREDIT = "credit"
    HOLD = "hold"
    RELEASE = "release"
    DEBIT = "debit"

class IdempotencyState(str, Enum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
```

---

## 5. Money Invariants

### 5.1 Balance derivation (single SQL, no joins)

```sql
SELECT
  COALESCE(SUM(CASE WHEN type='credit'  THEN amount_paise ELSE 0 END), 0)
- COALESCE(SUM(CASE WHEN type='hold'    THEN amount_paise ELSE 0 END), 0)
+ COALESCE(SUM(CASE WHEN type='release' THEN amount_paise ELSE 0 END), 0)
- COALESCE(SUM(CASE WHEN type='debit'   THEN amount_paise ELSE 0 END), 0)
  AS available_paise,

  COALESCE(SUM(CASE WHEN type='hold'    THEN amount_paise ELSE 0 END), 0)
- COALESCE(SUM(CASE WHEN type='release' THEN amount_paise ELSE 0 END), 0)
- COALESCE(SUM(CASE WHEN type='debit'   THEN amount_paise ELSE 0 END), 0)
  AS held_paise,

  COALESCE(SUM(CASE WHEN type='credit'  THEN amount_paise ELSE 0 END), 0)
  AS total_credits_paise

FROM transactions WHERE merchant_id = $1;
```

Implemented in `repositories/merchant_repo.py::get_balance_breakdown()` via Django ORM `Aggregate` + `Case`/`When`. Never compute balance in Python from fetched rows.

### 5.2 Invariants enforced

- `available_paise >= 0` always (cannot go negative — concurrency lock prevents it).
- `held_paise >= 0` always (mathematical: `hold` rows ≥ `release + debit` rows for same payout).
- For every `payout` in status `pending|processing`: exactly one `hold` txn references it.
- For every `payout` in status `completed`: exactly one `hold` and one `debit` txn reference it.
- For every `payout` in status `failed`: exactly one `hold` and one `release` txn reference it.

`ReconcileLedgerService` asserts these.

---

## 6. Critical Path: Payout Creation

`POST /api/v1/payouts` end-to-end:

```
INPUT
  Header:  Idempotency-Key (UUID)
  Body:    { amount_paise: int>0, bank_account_id: UUID }
  Context: merchant_id (resolved by middleware/DRF)

STEP 1 — Compute request_hash = sha256(canonical_json(body))

STEP 2 — Idempotency upsert (own short atomic block)
  INSERT INTO idempotency_records (merchant_id, key, request_hash, state='in_progress', expires_at=now()+24h)
    ON CONFLICT (merchant_id, idempotency_key) DO NOTHING
    RETURNING id;
  if not inserted:
    SELECT existing record.
    IF expires_at < now(): treat as absent → retry the INSERT (delete-and-insert pattern, or update-in-place via CTE)
    IF request_hash != incoming hash → 409 "key_reused_with_different_body"
    IF state == 'completed' → return stored (status_code, body) byte-identical
    IF state == 'in_progress' → poll loop (5 × 200ms = 1s):
        re-SELECT; if state == 'completed' return stored response.
      after timeout → 202 { "status": "processing", "payout_id": <or null>, "retry_after_ms": 1000 }

STEP 3 — Critical atomic block (the lock)
  with transaction.atomic():
    merchant_repo.lock_for_update(merchant_id)            # SELECT FOR UPDATE on merchants row
    breakdown = merchant_repo.get_balance_breakdown(...)  # single aggregation inside lock
    if breakdown.available_paise < amount_paise:
      raise InsufficientBalance
    payout = payout_repo.create(merchant, bank_account, amount, idempotency_key, status=PENDING)
    txn_repo.insert_hold(payout, amount)                  # the hold IS the fund reservation
    response_body = serialize(payout)
    idempotency_repo.update_with_response(record_id, payout_id=payout.id, status=201, body=response_body, state=COMPLETED)

STEP 4 — Outside the atomic block
  tasks.process_payout.delay(payout.id)
  return 201, response_body

ERROR PATHS
  InsufficientBalance:
    Inside the atomic block we DO NOT update idempotency record yet (rollback would lose it).
    Catch outside: open a new transaction, set idempotency_record.state=COMPLETED with status=422 + error body.
    return 422, { error: "insufficient_balance", available_paise, requested_paise }
  Validation error (bad UUID, missing field): 400 — no idempotency record created (we never reached step 2 with valid hash). Use DRF serializer validation.
```

Implemented in `services/create_payout.py::CreatePayoutService.execute()`.

---

## 7. Critical Path: Worker Lifecycle

`@shared_task process_payout(payout_id)` → `services/process_payout.py::ProcessPayoutService.execute(payout_id)`:

```
1. payout = payout_repo.get(payout_id)
   if payout.status != PENDING: return  # idempotent task entry — duplicate delivery safe

2. rows = payout_repo.transition(payout_id, frm=PENDING, to=PROCESSING,
                                 increment_attempt=True, on_apply=None)
   if rows == 0: return  # another worker claimed; this is fine

3. outcome = simulate_bank_settlement()  # random: 70% success, 20% fail, 10% hang
   if outcome == 'hang':
     return  # leave in PROCESSING; sweeper picks up after 30s

4. if outcome == 'success':
     payout_repo.transition(
       payout_id, frm=PROCESSING, to=COMPLETED,
       on_apply=lambda: txn_repo.insert_debit(payout, amount, reference="bank_settled"))
   else:  # outcome == 'fail'
     payout_repo.transition(
       payout_id, frm=PROCESSING, to=FAILED,
       on_apply=lambda: txn_repo.insert_release(payout, amount, reference="bank_failed"))
```

`payout_repo.transition()` runs the conditional UPDATE, the `on_apply` callback, and the `payout_event` insert **inside one atomic block**. This is what makes refund-on-failure atomic.

---

## 8. Critical Path: Stale Sweeper

Beat-scheduled task runs every 10s → `services/retry_stale.py::RetryStalePayoutsService.execute()`:

```sql
-- payout_repo.claim_stale_with_skip_locked(now, threshold)
SELECT id, attempt_count
FROM payouts
WHERE status = 'processing'
  AND last_attempted_at < now() - INTERVAL '30 seconds'
ORDER BY last_attempted_at
FOR UPDATE SKIP LOCKED
LIMIT 100;
```

For each claimed row:
- If `attempt_count >= 3`:
  - `payout_repo.transition(id, frm=PROCESSING, to=FAILED, on_apply=insert_release)` — atomic max-attempts failure with refund.
- Else:
  - Re-enqueue: `tasks.process_payout.apply_async(args=[id], countdown=2**attempt_count)` (exponential backoff: 1s, 2s, 4s).
  - Note: the `pending→processing` transition will fail (already in `processing`) — that's fine. Worker first-line check handles it. The actual progression happens when bank simulation runs again.

**Correction note:** the worker's step 1 currently returns if status != PENDING. The sweeper re-enqueues a payout already in PROCESSING. We have two clean options; pick:

- **Option A (selected):** sweeper performs `processing→processing` "kick" by writing a fresh `last_attempted_at` and re-running the simulation directly inside the sweeper service (not by re-enqueuing a worker task). Simpler. Sweeper IS the retry mechanism for stuck payouts.
- Option B (rejected): introduce a `retry_pending` intermediate state. Adds enum surface for no benefit.

Updated sweeper logic:
```
For each claimed row with attempt_count < 3:
  Update last_attempted_at = now(), attempt_count += 1 (still status=processing).
  Run simulate_bank_settlement() inline.
  Apply outcome (transition to completed/failed with on_apply, OR leave in processing for next sweep).
```

This keeps the sweeper as the single owner of retries-after-stall.

---

## 9. Critical Path: Reconciliation

`manage.py reconcile` → `services/reconcile_ledger.py::ReconcileLedgerService.execute()`:

For each merchant:
1. Compute `available, held, total_credits` from ledger (one aggregation query).
2. Sum `payouts.amount_paise` where `status IN (pending, processing)` → expected `held_from_payouts`.
3. Assert `held_from_payouts == held` (ledger view).
4. Per-payout invariant:
   - `pending|processing`: 1 hold txn, 0 release/debit txns.
   - `completed`: 1 hold, 1 debit, 0 release.
   - `failed`: 1 hold, 1 release, 0 debit.

Returns drift report. Exit code 0 if no drift, 1 otherwise.

---

## 10. Idempotency Protocol (canonical)

### 10.1 Three cases on conflict

| Existing record | Incoming hash | Action |
|---|---|---|
| `state=completed`, hash matches | match | Return stored `(status_code, body)` byte-identical |
| `state=completed`, hash differs | differ | `409 key_reused_with_different_body` |
| `state=in_progress`, hash matches | match | Poll 5×200ms → if completed return stored, else `202 processing { payout_id, retry_after_ms }` |
| `state=in_progress`, hash differs | differ | `409 key_reused_with_different_body` |
| `expires_at < now()` | any | Treat as absent; perform fresh INSERT |

### 10.2 Canonical JSON for hashing

`json.dumps(body, sort_keys=True, separators=(',', ':'), ensure_ascii=False)` then `sha256().hexdigest()`. Hash only fields the API contract consumes (`amount_paise`, `bank_account_id`); ignore unknown fields.

### 10.3 Expiry sweeper

Daily beat task: `DELETE FROM idempotency_records WHERE expires_at < now()`.

---

## 11. State Machine

### 11.1 Legal transitions

```
LEGAL = {
  ('pending', 'processing'),
  ('processing', 'completed'),
  ('processing', 'failed'),
}
```

All other transitions are illegal — including any backward, sideways, or self-loop. `failed→completed` is **structurally unreachable** because no entry permits it.

### 11.2 Single transition function

`repositories/payout_repo.py::transition(payout_id, frm, to, *, on_apply=None, reason=None, increment_attempt=False)`:

```python
def transition(payout_id, frm, to, *, on_apply=None, reason=None, increment_attempt=False):
    domain.transitions.validate(frm, to)  # raises InvalidStateTransition if (frm,to) not in LEGAL
    with transaction.atomic():
        update_kwargs = {"status": to, "updated_at": Now()}
        if increment_attempt:
            update_kwargs["attempt_count"] = F("attempt_count") + 1
            update_kwargs["last_attempted_at"] = Now()
        rows = (Payout.objects
                .filter(id=payout_id, status=frm)
                .update(**update_kwargs))
        if rows != 1:
            raise InvalidStateTransition(payout_id, frm, to, reason="status_mismatch")
        if on_apply is not None:
            on_apply()
        payout = Payout.objects.get(id=payout_id)  # for attempt_count snapshot
        PayoutEvent.objects.create(
            payout_id=payout_id, from_status=frm, to_status=to,
            attempt=payout.attempt_count, reason=reason)
        return rows
```

Every state change in the system goes through this function. EXPLAINER points here.

---

## 12. API Contracts

### 12.1 `POST /api/v1/payouts`

**Request**:
```
Headers:  Idempotency-Key: <uuid>  (required)
Body:     { "amount_paise": <int>0>, "bank_account_id": "<uuid>" }
```

**Responses**:
| Status | Body | When |
|---|---|---|
| 201 | full payout object | success |
| 202 | `{ "status": "processing", "payout_id": <uuid|null>, "retry_after_ms": 1000 }` | idempotency in-flight after poll timeout |
| 400 | DRF validation errors | malformed body / missing fields |
| 404 | `{ "error": "bank_account_not_found" }` | bank account missing or not owned by merchant |
| 409 | `{ "error": "key_reused_with_different_body" }` | idempotency payload mismatch |
| 422 | `{ "error": "insufficient_balance", "available_paise": <int>, "requested_paise": <int> }` | balance check fails |

Payout object shape (used in 201 and GET):
```json
{
  "id": "uuid",
  "merchant_id": "uuid",
  "bank_account_id": "uuid",
  "amount_paise": 100000,
  "status": "pending",
  "attempt_count": 0,
  "last_attempted_at": null,
  "created_at": "2026-04-25T10:00:00Z",
  "updated_at": "2026-04-25T10:00:00Z"
}
```

### 12.2 `GET /api/v1/merchants/{merchant_id}/balance`

```json
{
  "available_paise": 50000,
  "held_paise": 60000,
  "total_credits_paise": 110000
}
```

### 12.3 `GET /api/v1/merchants/{merchant_id}/transactions`

Paginated (DRF `LimitOffsetPagination`, default 50). Items:
```json
{
  "id": "uuid",
  "type": "credit|hold|release|debit",
  "amount_paise": 60000,
  "payout_id": "uuid|null",
  "reference": "string|null",
  "created_at": "iso8601"
}
```

### 12.4 `GET /api/v1/payouts?merchant_id={uuid}`

Paginated. Items: payout object shape above.

### 12.5 `GET /api/v1/payouts/{id}`

Single payout object.

### 12.6 `GET /api/v1/payouts/{id}/events` (admin/debug)

```json
[{ "from_status": "pending", "to_status": "processing", "attempt": 1, "reason": null, "created_at": "..." }, ...]
```

### 12.7 `GET /api/v1/merchants`

```json
[{ "id": "uuid", "name": "string" }, ...]
```

### 12.8 `GET /api/v1/merchants/{id}/bank_accounts`

```json
[{ "id": "uuid", "label": "string", "account_number_masked": "XXXX1234", "ifsc": "string" }, ...]
```

### 12.9 `GET /healthz`

```json
{ "db": "ok", "redis": "ok", "celery_ping": "ok|fail" }
```

---

## 13. Folder Structure

### 13.1 Backend

```
backend/
  config/
    __init__.py
    settings/{base,dev,prod,test}.py
    urls.py
    asgi.py
    wsgi.py
    celery.py
  apps/
    merchants/
      __init__.py
      models.py                    # Merchant, BankAccount
      api/
        views.py
        serializers.py
        urls.py
      management/commands/
    payouts/
      __init__.py
      models.py                    # Payout, Transaction, PayoutEvent, IdempotencyRecord
      domain/
        __init__.py
        enums.py
        transitions.py
        errors.py
        money.py
      repositories/
        __init__.py
        merchant_repo.py
        payout_repo.py
        transaction_repo.py
        idempotency_repo.py
        event_repo.py
      services/
        __init__.py
        create_payout.py
        process_payout.py
        retry_stale.py
        reconcile_ledger.py
        dashboard.py
      tasks/
        __init__.py
        process_payout.py
        sweep_stale.py
        expire_idempotency.py
      api/
        views.py
        serializers.py
        exceptions.py
        urls.py
      management/commands/
        seed.py
        reconcile.py
        stress_concurrency.py
  observability/
    __init__.py
    logging.py
    middleware.py
  tests/
    conftest.py
    integration/
      test_balance_aggregation.py
      test_concurrency_tier1.py
      test_concurrency_tier2.py
      test_idempotency_replay.py
      test_idempotency_in_flight.py
      test_idempotency_payload_mismatch.py
      test_state_machine_guards.py
      test_worker_success.py
      test_worker_failure_refund.py
      test_worker_hang_retry_max.py
      test_stale_sweeper.py
      test_reconciliation.py
    unit/
      test_domain_transitions.py
      test_money_helpers.py
      test_request_hash.py
  pyproject.toml
  manage.py
  Dockerfile
```

### 13.2 Frontend

```
frontend/
  src/
    api/
      client.ts                # fetch wrapper, idempotency-key injection, error parsing
      payoutsApi.ts
      merchantsApi.ts
      types.ts
    hooks/
      usePolling.ts
      useBalance.ts
      usePayouts.ts
      useTransactions.ts
      useCreatePayout.ts
      useMerchant.ts
    components/                # presentational only
      BalanceCard.tsx
      StatusBadge.tsx
      MoneyText.tsx
      PayoutRow.tsx
      TransactionRow.tsx
      TableShell.tsx
      FormField.tsx
      Button.tsx
    features/                  # composed slices
      MerchantSelector.tsx
      DashboardPanel.tsx
      PayoutForm.tsx
      PayoutHistorySection.tsx
      TransactionLedger.tsx
    utils/
      formatInr.ts             # ₹1,23,456.78 (Indian numbering)
      formatTimestamp.ts
      uuid.ts
      constants.ts
    App.tsx
    main.tsx
    index.css
  tailwind.config.ts
  vite.config.ts
  tsconfig.json
  package.json
  Dockerfile
```

---

## 14. Test Strategy

### 14.1 Real PostgreSQL only

`pytest-django` configured with PG via `DATABASE_URL` env var; no sqlite fallback. `--reuse-db` for speed; `--create-db` in CI. Test DB seeded via fixtures, not management commands.

### 14.2 Mandatory integration tests

| Test | Asserts |
|---|---|
| `test_balance_aggregation` | All 4 txn types contribute correctly to `available`/`held`/`total_credits` |
| `test_concurrency_tier1` | ₹100 merchant, two simultaneous ₹60 POSTs → exactly 1 success, 1 reject (422), balance never negative |
| `test_concurrency_tier2` | ₹300 merchant, 10 simultaneous ₹60 POSTs → exactly 5 succeed, 5 reject, sum of holds = ₹300 |
| `test_idempotency_replay` | Same key + same body twice → 1 payout in DB, both responses byte-identical |
| `test_idempotency_in_flight` | Same key, second arrives during first → 202 or stored response, never 2nd payout |
| `test_idempotency_payload_mismatch` | Same key, different body → 409 |
| `test_state_machine_guards` | Each illegal transition raises `InvalidStateTransition` |
| `test_worker_success` | `pending→processing→completed` writes debit txn, no release |
| `test_worker_failure_refund` | `pending→processing→failed` writes release txn atomically; balance restored |
| `test_worker_hang_retry_max` | 3 hangs → final state is `failed`, release written, attempt_count == 3 |
| `test_stale_sweeper` | Concurrent sweeper invocations don't double-claim; 30s threshold respected |
| `test_reconciliation` | Drift detection flags an artificially injected ledger row |

### 14.3 Concurrency mechanism

`ThreadPoolExecutor` with `max_workers=N`, each thread opens its own DB connection (no shared cursor). Use a `threading.Barrier` to release all threads simultaneously and maximize race window.

### 14.4 Optional senior-signal harness

`manage.py stress_concurrency --merchants 5 --workers 50 --requests 200`: invariant-fuzz across merchants, asserts ledger invariant on completion. Not required for grading; included for EXPLAINER.

---

## 15. Observability

### 15.1 Structured logs

`structlog` JSON renderer to stdout. Contextvars carry:
- `correlation_id` (UUID per HTTP request, generated by middleware; reused by Celery tasks via task header)
- `payout_id`, `merchant_id`, `idempotency_key`, `attempt_number` (added at the relevant call site)

### 15.2 Logged events (mandatory)

| Event | Where |
|---|---|
| `request.start` / `request.end` | middleware |
| `payout.created` | `CreatePayoutService` after commit |
| `payout.processing` | `transition(pending→processing)` |
| `payout.completed` | `transition(processing→completed)` |
| `payout.failed` | `transition(processing→failed)` |
| `payout.funds_released` | `txn_repo.insert_release()` |
| `payout.retry_scheduled` | sweeper inline retry |
| `payout.max_attempts_exceeded` | sweeper failure path |
| `idempotency.replayed` | Case A return |
| `idempotency.in_flight` | Case B 202 return |
| `idempotency.payload_mismatch` | Case C 409 return |
| `concurrency.lock_acquired` | DEBUG level only, after `lock_for_update` |

### 15.3 Trace example (target for EXPLAINER)

```bash
jq 'select(.payout_id == "abc...")' logs.json
```
Returns: created → processing → completed (or fail/release/retry sequences) for that payout in chronological order, with full context.

---

## 16. Deployment

### 16.1 docker-compose services

```yaml
services:
  db:        # postgres:16
  redis:     # redis:7
  web:       # backend Django + DRF (gunicorn)
  worker:    # celery worker
  beat:      # celery beat
  frontend:  # built Vite assets served by nginx, OR built into web image
```

`make up` runs `docker compose up -d --build`. `make seed` runs `docker compose exec web python manage.py seed`.

### 16.2 Railway

- PostgreSQL plugin
- Redis plugin
- 3 services: `web`, `worker`, `beat`
- Frontend either deployed as a separate Railway static site or served from `web` (whichever is simpler at deploy time).
- Single `DATABASE_URL` and `REDIS_URL` env vars across all services.

### 16.3 Configuration

`config/settings/{base,dev,prod,test}.py`. Env-driven via `os.environ`. Required vars: `DATABASE_URL`, `REDIS_URL`, `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`.

### 16.4 Makefile

```
make up         # docker compose up -d --build
make down       # docker compose down -v
make seed       # exec web ./manage.py seed
make test       # exec web pytest
make stress     # exec web ./manage.py stress_concurrency
make reconcile  # exec web ./manage.py reconcile
make logs       # docker compose logs -f web worker beat
make fmt        # ruff format
```

---

## 17. EXPLAINER.md Sections (canonical)

1. **Architecture at a Glance** — diagram + paragraph describing API → Services → Repositories → DB; Tasks → Services → Repositories. Why the split.
2. **The Ledger** — paste 4-type aggregation query from `merchant_repo.get_balance_breakdown()` + `EXPLAIN ANALYZE` output. Why credit/hold/release/debit instead of credit/debit + payout-status join.
3. **The Lock** — paste the entire `CreatePayoutService.execute()` critical block. Explain `SELECT FOR UPDATE` row-level lock. Reference Tier-1 + Tier-2 tests.
4. **The Idempotency** — paste `idempotency_repo.insert_or_get_by_key()`. Walk Cases A/B/C. Explain why `request_hash` matters.
5. **The State Machine** — paste `payout_repo.transition()`. Explain conditional UPDATE WHERE clause as the DB guard. Show `LEGAL` table and explain `failed→completed` is structurally unreachable.
6. **Atomic Refund** — paste the failure-path call: `transition(frm=PROCESSING, to=FAILED, on_apply=lambda: insert_release(...))`. Explain why state and money commit together.
7. **Failure Recovery** — paste sweeper `claim_stale_with_skip_locked()`. Cover crash-after-mark, duplicate delivery, bank hang, max attempts.
8. **Observability** — paste a real structured-log trace of one payout end-to-end. Show the `jq` filter.
9. **AI Audit** — one real example of subtly wrong AI suggestion caught (e.g., balance check outside atomic block; refund in separate transaction). Paste before/after, explain why the original was wrong.

---

## 18. Out of Scope

- Authentication / multi-tenancy beyond merchant resolution stub (selector in UI)
- Customer payment ingestion (seeded credits only)
- Webhook delivery
- Event sourcing / CQRS
- WebSockets / live updates beyond polling
- Multi-currency (everything is INR paise)
- Pixel-perfect UI / animations
- Pre-prod auth flows / OAuth
- Microservices split

---

## 19. Risk Register

| Risk | Mitigation |
|---|---|
| Test concurrency flake on real PG | Use `threading.Barrier`, set `connect_args={'options': '-c statement_timeout=5000'}`, retry once on flake before failing |
| Celery task acks-on-receipt loses work on crash | Use `acks_late=True`, `task_reject_on_worker_lost=True`, and rely on sweeper for stuck rows |
| Idempotency record orphaned (in_progress, payout creation crashed before update) | Sweeper purges expired records (24h); 24h is acceptable for the grading window |
| docker-compose port clash on dev machine | Document port-override env vars in README |
| Railway free-tier service sleep | Document; healthz endpoint should wake services |

---

## 20. Glossary

- **Hold**: a `transactions` row of type `hold`, written when a payout is created, reserving funds.
- **Release**: a `transactions` row of type `release`, written on payout failure, returning held funds.
- **Debit**: a `transactions` row of type `debit`, written on payout completion, finalizing fund movement.
- **Lock anchor**: the `merchants` row, locked via `SELECT FOR UPDATE` at the start of every payout creation flow.
- **Critical path**: the `CreatePayoutService.execute()` flow from idempotency check through `tasks.delay()`.
- **Sweeper**: the beat-scheduled `RetryStalePayoutsService` that claims stuck-in-processing payouts via `SELECT FOR UPDATE SKIP LOCKED`.

---

## 21. Self-Review (passed)

- [x] No placeholders.
- [x] No contradictions: ledger model, balance derivation, idempotency cases, state-machine, sweeper retry mechanism are consistent across §4, §5, §6, §7, §8, §10, §11.
- [x] No scope creep: stack matches v2 plan; nothing added since user approval.
- [x] Sweeper mechanism resolved (Option A — sweeper does the retry inline; tasks aren't re-enqueued for stuck payouts).
- [x] Idempotency expiry path handled in §6 step 2 and §10 row 5.
- [x] Error-path idempotency record update spelled out in §6 ERROR PATHS.
- [x] All API contracts have explicit status codes and bodies.
- [x] Test list covers every acceptance criterion in §1.
- [x] EXPLAINER sections trace to specific code paths.
