# EXPLAINER

---

## 1. The Ledger

```python
row = Transaction.objects.filter(merchant_id=merchant_id).aggregate(
    credits=Sum(Case(When(type="credit", then=F("amount_paise")), default=Value(0), output_field=IntegerField())),
    holds=Sum(Case(When(type="hold",   then=F("amount_paise")), default=Value(0), output_field=IntegerField())),
    releases=Sum(Case(When(type="release", then=F("amount_paise")), default=Value(0), output_field=IntegerField())),
    debits=Sum(Case(When(type="debit", then=F("amount_paise")), default=Value(0), output_field=IntegerField())),
)

available_paise = credits - holds + releases - debits
held_paise      = holds - releases - debits
```

**Why this model:**

- No mutable balance column — there is no `UPDATE merchants SET balance = balance - X` anywhere. That eliminates lost-update anomalies at the balance level entirely.
- Append-only log — every rupee movement is a row. Audit is a `SELECT`; reversal is an insert, not an edit.
- Four types map directly to the payout lifecycle: `credit` (funds in) → `hold` (reserved on payout create) → `release` (returned on failure) or `debit` (finalised on success).
- The aggregate runs in one round-trip. It is O(n transactions), which is acceptable because the hot path serialises on a row-level lock before this query runs.

---

## 2. The Lock

```python
def _run_critical_path(self, record_id: str) -> tuple[int, dict]:
    with db_transaction.atomic():
        merchant = merchant_repo.lock_for_update(self.merchant_id)  # SELECT … FOR UPDATE

        balance = merchant_repo.get_balance_breakdown(self.merchant_id)
        if balance.available_paise < self.amount_paise:
            raise InsufficientBalance(...)

        payout = payout_repo.create_with_hold(merchant, bank_account, self.amount_paise)
        idempotency_repo.attach_payout(record_id, str(payout.id))
    # transaction commits here — lock released, payout_id FK stamped on idempotency record
```

**DB primitive:** PostgreSQL row-level lock via `SELECT … FOR UPDATE`.

`lock_for_update()` issues `SELECT id FROM merchants WHERE id = %s FOR UPDATE`. PostgreSQL blocks any other transaction that tries to lock the same row until this one commits or rolls back. The balance check and the hold insert are inside the same `atomic()` block — there is no window between "read balance" and "write hold" where another request can observe the pre-hold state. Two concurrent ₹60 requests against a ₹100 merchant cannot both pass the balance check; the second blocks at the lock, re-reads the balance after the first commits, and sees insufficient funds.

---

## 3. The Idempotency

**How the system knows it has seen a key:**

```python
record, created = IdempotencyRecord.objects.get_or_create(
    merchant_id=merchant_id,
    idempotency_key=key,
    defaults={"request_hash": request_hash, "state": IN_FLIGHT, ...},
)
```

`get_or_create` is atomic. If the key exists, `created=False` and we branch into replay logic. If not, `created=True` and the request proceeds.

A SHA-256 hash of the request body is stored alongside the key. If a retry arrives with the same key but a different body, we return 409 (`IdempotencyPayloadMismatch`) — the caller cannot silently change amount or bank account under the same key.

**If the first request is still in flight when the second arrives:**

```python
def _handle_existing_record(self, record):
    if record.state == IdempotencyState.COMPLETED:
        stored = dict(record.response_body)
        status = stored.pop("_status", 201)
        return status, stored                    # byte-identical replay

    record.refresh_from_db()
    if record.payout_id:
        payout = Payout.objects.get(id=record.payout_id)
        return 200, {"id": str(payout.id), "status": payout.status, ...}

    # microsecond window: record inserted but attach_payout not yet called
    return 202, {"status": "in_flight", "retry_after_ms": 500}
```

`attach_payout()` stamps the `payout_id` FK on the idempotency record inside the same atomic block that creates the payout. So by the time the first request's transaction commits, any duplicate can `refresh_from_db()`, find the FK, and return live payout state immediately — no polling, no sleeping. The 202 path is only hit in a sub-millisecond window between the record insert and the `attach_payout()` call completing.

---

## 4. The State Machine

**The check lives in two independent places, either of which is sufficient:**

```python
LEGAL = {
    (PayoutStatus.PENDING,     PayoutStatus.PROCESSING),
    (PayoutStatus.PROCESSING,  PayoutStatus.COMPLETED),
    (PayoutStatus.PROCESSING,  PayoutStatus.FAILED),
}

def validate(frm, to) -> None:
    if (frm, to) not in LEGAL:
        raise InvalidStateTransition(frm=frm, to=to)
```

`(FAILED, COMPLETED)` is not in `LEGAL`. `validate()` raises before any DB write.

```python
rows = Payout.objects.filter(id=payout_id, status=frm).update(status=to)
if rows == 0:
    raise InvalidStateTransition(frm=frm, to=to)
```

Even if `validate()` were bypassed, the WHERE clause filters on `status=frm`. A FAILED payout has `status='failed'`, so `filter(..., status='processing')` matches zero rows and raises anyway. The DB enforces the invariant independently of the application layer.

---

## 5. The AI Audit

**What the AI generated** (worker-side bank settlement):

```python
def simulate_bank_settlement(seed=None) -> str:
    r = seed if seed is not None else random.random()
    if r < 0.70: return "success"
    if r < 0.90: return "fail"
    return "hang"

class ProcessPayoutService:
    def execute(self):
        outcome = simulate_bank_settlement(self.settlement_seed)
        if outcome == "hang":
            return "hung"          # payout left in PROCESSING, worker exits
        if outcome == "success":
            with db_transaction.atomic():
                payout_repo.transition(... to=COMPLETED, on_apply=insert_debit ...)
        else:
            with db_transaction.atomic():
                payout_repo.transition(... to=FAILED, on_apply=insert_release ...)
```

**What I caught — three concrete problems:**

1. **No I/O boundary.** A random number generator inside the same process cannot demonstrate timeout handling, network failure, or partial-failure modes — the scenarios that actually matter in production.

2. **"hang" semantics are wrong.** Returning `"hung"` and abandoning the payout in PROCESSING models a worker that gave up, not a bank that accepted the request silently. The retry path should re-fire the HTTP call; instead, each sweeper cycle runs a fresh coin flip — a completely different (and wrong) outcome distribution.

3. **The idempotency poll was load-bearing on synchrony.** The 5 × 200 ms sleep loop in `CreatePayoutService._handle_existing_record()` only worked because settlement was synchronous — the payout was COMPLETED before a duplicate request arrived. With any real async provider the poll always exhausts and every duplicate returns 202.

**What replaced it:** A separate `bank_simulator/` FastAPI service.

- `ProcessPayoutService` fires `httpx.post(/settle)` and returns immediately.
- The simulator rolls an outcome and fires `POST /api/v1/webhooks/bank-callback/` back after 100–400 ms.
- For the 10% "pending" case it fires no callback; the sweeper re-fires the HTTP call on the next cycle — correctly modelling a provider that accepted but went silent.
- `BankCallbackView` calls `payout_repo.transition()` with the appropriate `on_apply` ledger operation. Status flip and ledger insert commit together inside one `atomic()`, same guarantee as the original inline path.
- The idempotency poll was removed entirely. The `payout_id` FK is stamped on the `IdempotencyRecord` inside the creation transaction; duplicates read live state from the FK with no sleeping.

The sleep loop disappeared as a side effect. The durable outcome was an architecture that mirrors a real provider integration: HTTP call out, async callback in, no-callback as the hang case, sweeper retry, and a webhook endpoint that is genuinely idempotent on re-delivery.
