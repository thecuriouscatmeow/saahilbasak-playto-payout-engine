---
id: DEC-001
title: Extract bank settlement into a separate HTTP service
status: Accepted
date: 2026-04-29
---

## Context

The original implementation called `simulate_bank_settlement()` inline inside `ProcessPayoutService.execute()`. This is a pure Python coin-flip that runs in the same process as the payout engine. Three consequences:

1. **No real I/O boundary.** The "bank" is a random number generator. There is no network call, no timeout surface, no partial-failure mode to test against. An interviewer reviewing the code sees no evidence that the author knows how provider integrations actually work.

2. **The sleep loop is load-bearing.** `CreatePayoutService._handle_existing_record()` polls `time.sleep(0.2) × 5` waiting for a duplicate-key record to flip from IN_FLIGHT to COMPLETED. This works only because settlement is synchronous — by the time the second HTTP request arrives, the worker has already called `simulate_bank_settlement()` and transitioned the payout. With async outcomes this assumption breaks.

3. **The 10% "hang" outcome is inexpressive.** Returning `"hung"` and leaving the payout in PROCESSING correctly exercises the sweeper, but it doesn't model what actually happens: the provider accepted the request but sent no callback. The distinction matters for reasoning about retry semantics.

## Decision

Extract bank settlement into a standalone `bank_simulator/` FastAPI service with:
- `POST /settle` — accepts `{payout_id, amount_paise, callback_url}`, responds 200 immediately, fires a delayed callback asynchronously
- No callback for the 10% "pending" outcome (models a provider that hangs, not one that crashes)
- `ProcessPayoutService` fires `httpx.post()` and returns; the webhook handler drives all terminal transitions
- `RetryStalePayoutsService` re-fires the HTTP call outside the DB transaction (no holding locks during network I/O)

The sleep loop is deleted as a side effect. `idempotency_repo.attach_payout()` stamps the payout FK onto the idempotency record inside the atomic block so duplicate requests return live payout state immediately.

## Consequences

**Gained:**
- Real HTTP boundary with timeout handling and a silent-failure path
- The 10% hang case is now "no callback arrives" — semantically correct and sweeper-testable
- Idempotency duplicate path is instant (no polling)
- Worker tests drive outcomes via webhook calls rather than seeded random — closer to integration behavior
- EXPLAINER §10 has a concrete architecture evolution story

**Lost / accepted:**
- More moving parts to start locally (`docker compose up` handles it)
- Worker and sweeper tests now require mocking `httpx.post` and manually invoking `BankCallbackView` — slightly more test setup
- No HMAC verification on the webhook (explicitly out of scope; noted in EXPLAINER)
