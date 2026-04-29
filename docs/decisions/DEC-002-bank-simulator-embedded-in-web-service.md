---
id: DEC-002
title: Embed bank simulator in the web service for Railway free-tier deployment
status: Accepted
date: 2026-04-29
supersedes: partial constraint on DEC-001
---

## Context

Railway's free plan enforces a workspace-level resource cap. The `playto-payout-engine` project already uses five services: **web**, **worker**, **Postgres**, **Redis**, **frontend**. Attempting to provision a sixth service (`bank_simulator`) returns:

```
Free plan resource provision limit exceeded. Please upgrade to provision more resources!
```

The same cap applies to new projects in the same workspace. A sixth slot requires a paid plan (Hobby, $5/month).

## Decision

Embed the bank simulator logic as a Django view within the existing web service:

```
POST /api/v1/bank-simulator/settle/  →  BankSimulatorSettleView
```

The view:
1. Accepts the same `{payout_id, amount_paise, callback_url}` body as the standalone FastAPI service
2. Rolls the 70/20/10 outcome
3. Fires a `threading.Thread` callback to `callback_url` after a 100–400ms sleep (daemon thread, fire-and-forget)
4. Returns `{"accepted": true, "outcome_will_be": "..."}` immediately

Environment variable wiring on Railway:
- `BANK_SIMULATOR_URL=http://web.railway.internal:8000/api/v1/bank-simulator` (worker → web, internal private network)
- `ENGINE_WEBHOOK_URL=http://web.railway.internal:8000/api/v1/webhooks/bank-callback/` (web → web, internal)

The HTTP boundary is preserved: `ProcessPayoutService` fires a real `httpx.post()` across Railway's private network to the web service, which fires a real `httpx.post()` back to the webhook endpoint on itself. Both calls traverse the network stack; they are not in-process calls.

The standalone `bank_simulator/` FastAPI service remains in the repository for local `docker compose up` (where the 5-service limit does not apply).

## Consequences

**Accepted trade-off:**
- The bank simulator and payout engine share a process in the Railway deployment. This is architecturally weaker than a true separate service: a bug in the simulator could affect the web process, and scaling them independently is not possible.
- For an interview submission this is immaterial. The code architecture is clean; only the deployment topology is constrained by the free plan.

**Preserved:**
- The real HTTP round-trip between worker and bank simulator, and between bank simulator and webhook handler
- All 93 tests pass; tests use `mock httpx.post` and invoke `BankCallbackView` directly, so they are unaffected by deployment topology
- The standalone `bank_simulator/` service is ready to deploy the moment a paid plan slot is available

**Upgrade path:**
- Upgrade Railway plan → provision `bank_simulator` as a separate service from `bank_simulator/` → set `BANK_SIMULATOR_URL` on web/worker to the new service's private domain → remove `BankSimulatorSettleView` and its URL from the Django app
