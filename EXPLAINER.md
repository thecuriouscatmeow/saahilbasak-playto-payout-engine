# EXPLAINER

## 1. Architecture at a Glance

```
React (Vite)
    │  HTTP / JSON
    ▼
Django REST Framework (views / serializers)
    │
    ▼
Services  (CreatePayoutService, ProcessPayoutService, RetryStalePayoutsService)
    │                          │
    ▼                          ▼
Repositories              Domain layer
(merchant_repo,           (transitions.py, errors.py,
 payout_repo,              enums.py, money.py)
 idempotency_repo,
 transaction_repo)
    │
    ▼
PostgreSQL ←──── Redis / Celery (async task queue)
```

The backend is four layers. Views handle HTTP concerns (auth, serialization, status codes) and nothing more. Services own the use-case logic — they orchestrate repositories and domain rules, but they never import a Django model directly. Repositories are the only layer that touches the ORM; they return plain Python objects or dataclasses upward. The domain layer is pure Python with no Django imports: transition rules, error types, and money helpers live here.

The strict "services never import models" rule has a concrete payoff: if we move a table to raw SQL, a microservice, or a read replica, only the repository changes. The service doesn't know whether `merchant_repo.lock_for_update()` is hitting `Merchant.objects.select_for_update().get(...)` or a `SELECT ... FOR UPDATE` via `connection.cursor()`. That boundary is the seam we can cut along later.

## 2. The Ledger

The merchant balance is never stored in a column. It is always derived by aggregating the `transactions` table. Every financial event appends a row with one of four `type` values — `credit`, `hold`, `release`, `debit` — and the current balance is whatever that append-only log says it is.

```python
def get_balance_breakdown(merchant_id: str) -> BalanceBreakdown:
    row = Transaction.objects.filter(merchant_id=merchant_id).aggregate(
        credits=Sum(
            Case(When(type="credit", then=F("amount_paise")), default=Value(0), output_field=IntegerField())
        ),
        holds=Sum(
            Case(When(type="hold", then=F("amount_paise")), default=Value(0), output_field=IntegerField())
        ),
        releases=Sum(
            Case(When(type="release", then=F("amount_paise")), default=Value(0), output_field=IntegerField())
        ),
        debits=Sum(
            Case(When(type="debit", then=F("amount_paise")), default=Value(0), output_field=IntegerField())
        ),
    )
    credits = row["credits"] or 0
    holds = row["holds"] or 0
    releases = row["releases"] or 0
    debits = row["debits"] or 0

    return BalanceBreakdown(
        available_paise=credits - holds + releases - debits,
        held_paise=holds - releases - debits,
        total_credits_paise=credits,
    )
```

The four-type accounting model maps cleanly to a payout lifecycle: a credit adds funds, a hold reserves them when a payout is created, a release returns them if the payout fails, and a debit finalises them when the payout completes. There is no `UPDATE merchants SET balance = balance - X` statement anywhere in the codebase. That means there is no mutable column to race on, no "lost update" anomaly possible at the balance level, and every rupee movement is trivially auditable by reading the transactions log in chronological order. The single aggregate query runs in one round-trip and is O(n transactions), which is acceptable because the hot path is protected by the `SELECT FOR UPDATE` lock described in the next section.

## 3. The Lock

Concurrent payout requests for the same merchant serialize on a row-level lock, not an application-level mutex. The lock is acquired at the start of the critical path and held for the duration of the balance check and payout creation.

```python
def _run_critical_path(self) -> tuple[int, dict]:
    with db_transaction.atomic():
        merchant = merchant_repo.lock_for_update(self.merchant_id)

        try:
            bank_account = BankAccount.objects.get(
                id=self.bank_account_id, merchant=merchant, is_active=True
            )
        except BankAccount.DoesNotExist:
            raise BankAccountNotFound(account_id=self.bank_account_id)

        balance = merchant_repo.get_balance_breakdown(self.merchant_id)
        if balance.available_paise < self.amount_paise:
            raise InsufficientBalance(
                merchant_id=self.merchant_id,
                requested_paise=self.amount_paise,
                available_paise=balance.available_paise,
            )

        payout = payout_repo.create_with_hold(merchant, bank_account, self.amount_paise)

    from apps.payouts.tasks.payout_tasks import process_payout
    from observability.correlation import get_correlation_id
    process_payout.apply_async(
        args=[str(payout.id)],
        kwargs={"correlation_id": get_correlation_id()},
    )
    ...
```

`merchant_repo.lock_for_update()` issues `SELECT ... FOR UPDATE` on the `merchants` row. PostgreSQL blocks any other transaction attempting to lock the same row until this transaction commits or rolls back. This means two concurrent requests for the same merchant cannot both read the balance, both see it as sufficient, and both insert a hold — only one proceeds at a time. The balance check (`get_balance_breakdown`) and the hold insert (`create_with_hold`) are inside the same `atomic()` block, so there is no window between "check" and "debit" where another thread can observe the pre-hold balance.

The concurrency tests prove this is not just theoretical. `test_concurrency_tier1.py` fires two simultaneous ₹60 requests at a ₹100 merchant using a `threading.Barrier` to synchronise thread start, and asserts `sorted(results) == [201, 422]` — exactly one success, one rejection, zero overdraft. `test_concurrency_tier2.py` scales this to ten simultaneous ₹60 requests at a ₹300 merchant and asserts exactly five succeed, the held total equals ₹300, and `available_paise == 0`. Both tests use `transaction=True` and close connections between threads to force real PostgreSQL concurrency rather than SQLite in-memory serialisation.

## 4. The Idempotency

Every payout creation request carries an `Idempotency-Key` header. The key is stored in `idempotency_records` alongside a SHA-256 hash of the request body. The first request creates the record atomically; subsequent requests look it up.

```python
def insert_or_get_by_key(
    merchant_id: str,
    key: str,
    request_hash: str,
    expires_at: datetime,
) -> tuple[IdempotencyRecord, bool]:
    with db_transaction.atomic():
        # Delete expired record for this key so it's treated as absent
        IdempotencyRecord.objects.filter(
            merchant_id=merchant_id,
            idempotency_key=key,
            expires_at__lt=timezone.now(),
        ).delete()

        record, created = IdempotencyRecord.objects.get_or_create(
            merchant_id=merchant_id,
            idempotency_key=key,
            defaults={
                "request_hash": request_hash,
                "state": IdempotencyState.IN_FLIGHT,
                "expires_at": expires_at,
            },
        )
    return record, created
```

When `created=False` the service enters `_handle_existing_record()`, which covers three cases. Case A: the record is `COMPLETED` — the stored `response_body` (which packs `_status` alongside the payout fields) is returned verbatim. The caller receives a byte-identical replay of the original 201 response; no new payout is created. Case B: the record is `IN_FLIGHT` — the original request is still being processed. The service polls 5×200 ms, and if the record has not transitioned to COMPLETED by then returns a 202 with `retry_after_ms: 1000`. Case C: `record.request_hash != self.request_hash` — the same key was reused with a different request body, which raises a 409 `IdempotencyPayloadMismatch`. The `request_hash` is essential for Case C: without it, a caller could silently change the amount or bank account on a retry and the system would replay the original response while the caller believed they had submitted a different payout. The hash makes that mismatch detectable and explicit rather than a silent data inconsistency.

## 5. The State Machine

State transitions are governed by an explicit allowlist. Any pair not in `LEGAL` is structurally unreachable — the domain layer raises before any database write can occur.

```python
LEGAL = {
    (PayoutStatus.PENDING, PayoutStatus.PROCESSING),
    (PayoutStatus.PROCESSING, PayoutStatus.COMPLETED),
    (PayoutStatus.PROCESSING, PayoutStatus.FAILED),
}


def validate(frm: PayoutStatus, to: PayoutStatus) -> None:
    if (frm, to) not in LEGAL:
        raise InvalidStateTransition(frm=frm, to=to)
```

The repository's `transition()` function pairs the domain-layer `validate()` call with a database-level WHERE-clause guard:

```python
def transition(
    payout_id: str,
    *,
    frm: PayoutStatus,
    to: PayoutStatus,
    on_apply=None,
    reason: str = "",
    increment_attempt: bool = False,
) -> int:
    validate(frm, to)

    update_kwargs = {"status": to}
    if increment_attempt:
        update_kwargs["attempts"] = F("attempts") + 1
        update_kwargs["last_attempted_at"] = timezone.now()

    rows = Payout.objects.filter(id=payout_id, status=frm).update(**update_kwargs)
    if rows == 0:
        raise InvalidStateTransition(frm=frm, to=to)

    event_repo.append(payout_id, frm=frm, to=to, reason=reason)
    log.info(f"payout.{to}", payout_id=payout_id, from_status=str(frm), to_status=str(to), reason=reason)

    if on_apply is not None:
        on_apply()

    return rows
```

`Payout.objects.filter(id=payout_id, status=frm).update(status=to)` will match zero rows if the payout has already been advanced by another worker. This turns what would otherwise be an application-layer assumption ("I believe this payout is PENDING") into a database-enforced assertion ("update only if the row currently says PENDING"). If `rows == 0`, `InvalidStateTransition` is raised regardless of whether the cause was a stale read or an illegal pair — the latter is already caught by `validate()` before the UPDATE fires.

The `failed → completed` path is structurally unreachable in two independent ways: `LEGAL` does not contain `(FAILED, COMPLETED)`, so `validate()` raises immediately, and even if someone patched `validate()`, the WHERE clause would find zero rows because a FAILED payout will never have `status=PROCESSING` when a completion transition is attempted.

## 6. Atomic Refund

When a payout fails — whether during initial processing or a sweeper retry — the balance release and the status update must commit together or not at all. This is enforced by the `on_apply` callback pattern.

```python
        # outcome == "fail"
        with db_transaction.atomic():
            payout_repo.transition(
                self.payout_id,
                frm=PayoutStatus.PROCESSING,
                to=PayoutStatus.FAILED,
                on_apply=lambda: transaction_repo.insert_release(payout, payout.amount_paise),
                reason="bank_failed",
            )
```

The `on_apply` lambda is called inside `transition()` after the UPDATE succeeds but before `atomic()` commits. If `insert_release()` raises — say, a database error or a constraint violation — the exception propagates out, `atomic()` rolls back, and the UPDATE to FAILED is undone. The payout stays in PROCESSING. Conversely, if the UPDATE fails (`rows == 0`), `on_apply` is never called, so the release INSERT never runs. State and money always move together: there is no code path that marks a payout FAILED without inserting a corresponding release, and no path that inserts a release without marking the payout FAILED. The same invariant holds in `RetryStalePayoutsService._handle_stale()` when the sweeper exhausts `MAX_ATTEMPTS`.

## 7. Failure Recovery

The sweeper (`RetryStalePayoutsService`) handles payouts that have been in PROCESSING too long. It uses raw SQL with `SKIP LOCKED` so that multiple sweeper instances running concurrently don't all grab the same stuck payouts.

```python
def claim_stale_with_skip_locked(threshold_seconds: int = 30, limit: int = 100) -> list:
    from django.db import connection
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT id, attempts
            FROM payouts
            WHERE status = 'processing'
              AND last_attempted_at < now() - make_interval(secs => %s)
            ORDER BY last_attempted_at
            FOR UPDATE SKIP LOCKED
            LIMIT %s
            """,
            [threshold_seconds, limit],
        )
        return cur.fetchall()
```

There are four failure scenarios this covers:

**Crash-after-mark**: A Celery worker picked up the payout, set it to PROCESSING via `transition(..., increment_attempt=True)`, then the process died before calling the bank. The payout is now stuck in PROCESSING with `last_attempted_at` in the past. After `threshold_seconds` the sweeper claims it and retries inline.

**Duplicate delivery**: Celery can deliver a task more than once. `ProcessPayoutService.execute()` checks `if payout.status != PayoutStatus.PENDING: return "already_handled"` as its first line. If a sweeper or a second task delivery finds the payout already in PROCESSING or COMPLETED, it returns immediately without touching the ledger.

**Bank hang**: `simulate_bank_settlement()` can return `"hung"` (10% probability), representing a bank API that accepted the request but gave no definitive answer. The worker returns `"hung"` and leaves the payout in PROCESSING. On the next sweeper cycle, `last_attempted_at` will be old enough to be picked up again for an inline retry.

**Max attempts**: If `attempts >= MAX_ATTEMPTS` (3), the sweeper atomically transitions to FAILED and calls `transaction_repo.insert_release()` via the same `on_apply` pattern described in section 6. The merchant's held funds are returned to available balance, and no further retries occur.

## 8. Observability

Every request and every Celery task carries a `correlation_id` that propagates through the full lifecycle of a payout without any manual log-call threading.

```python
@contextmanager
def bind_correlation_id(correlation_id: str = ""):
    cid = correlation_id or str(uuid.uuid4())
    structlog.contextvars.bind_contextvars(correlation_id=cid)
    try:
        yield cid
    finally:
        structlog.contextvars.unbind_contextvars("correlation_id")
```

```python
def configure_logging() -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
    )
```

`CorrelationIdMiddleware` calls `bind_correlation_id()` at the start of each request, reading from `X-Correlation-Id` header if provided or generating a fresh UUID. Because `structlog.contextvars.merge_contextvars` runs as the first processor on every log call, the `correlation_id` appears automatically in every structured log line emitted during that request — no one needs to pass it explicitly to `log.info()`. When `_run_critical_path()` enqueues the Celery task it passes `kwargs={"correlation_id": get_correlation_id()}`, threading the same ID across the process boundary. The worker calls `bind_correlation_id(correlation_id)` at task entry, so all worker-side logs carry the same ID. Running `jq 'select(.correlation_id == "abc123")' logs.jsonl` reconstructs the complete lifecycle of a single payout — API request, payout creation, bank settlement, and any sweeper retries — as a single ordered trace without a distributed tracing backend.

## 9. AI Audit

One real example where AI-generated code was wrong and what replaced it.

**Wrong suggestion:** When asked to implement balance checking, an AI suggested:

```python
merchant = Merchant.objects.get(id=merchant_id)
if merchant.balance >= amount:
    merchant.balance -= amount
    merchant.save()
```

**Why it's wrong:** There is no `balance` column — balance is derived from the transaction ledger. More critically, this pattern has a classic TOCTOU (time-of-check / time-of-update) race: two concurrent requests both read `balance = 100`, both see it as sufficient for `60`, both proceed, and the balance goes to `-20` after both `.save()` calls. The ORM `save()` issues `UPDATE merchants SET balance = <new_value>` with no WHERE guard on the old value. No lock, no atomicity, and the ledger-append model is completely bypassed.

**What replaced it:** `SELECT FOR UPDATE` on the Merchant row inside `transaction.atomic()`, followed by `get_balance_breakdown()` which does a single conditional-aggregate SQL query over the transactions table. The lock serializes concurrent requests at the database level; the balance check and hold insert (`create_with_hold`) happen inside the same atomic block so no other transaction can observe the pre-hold state. The balance is never stored — it is always derived — so there is no stale column to read, no mutable field to race on, and the full history of every balance movement is preserved in the append-only transactions log.
