# SRS — Playto Payout Engine
> Coding agent reference. Token-optimized, insight-dense. Strip all submission/deadline noise.

```json
{
  "meta": {
    "document": "SRS - Playto Payout Engine Challenge",
    "purpose": "Coding agent reference — compressed, insight-dense, covers explicit + implicit requirements",
    "date": "2026-04-24"
  },

  "company": {
    "name": "Playto",
    "url": "playto.so",
    "product": "Creator monetization platform — communities, courses, memberships, payments under one roof",
    "real_problem": "Indian creators, agencies, and freelancers are locked out of Stripe and PayPal. Playto is building cross-border payment infrastructure: collect USD from international customers, settle INR to Indian bank accounts in <7 days at a flat 4% vs competitors 4.4–5.7%+. The payout engine is the float manager — it holds merchant funds between USD collection and INR settlement. This is where regulatory risk, settlement timing, and engineering correctness all collide.",
    "strategic_signal": "This challenge IS Playto Pay's core engine. Solving it correctly signals you understand the hard part of their business — not just the tutorial version of payments."
  },

  "challenge_goal": "Build a merchant payout engine: balance visibility, payout request, payout lifecycle tracking. The graded surface is concurrency + idempotency + data integrity. Features are secondary.",

  "tech_stack": {
    "backend": "Django + DRF",
    "frontend": "React + Tailwind",
    "database": "PostgreSQL (required)",
    "background_jobs": "Celery | Django-Q | Huey — pick one. MUST run in a real worker process.",
    "hard_constraint": "No sync stubs for async jobs. Background processing must actually be async."
  },

  "data_model": {
    "currency_unit": "paise — integer only",
    "field_type": "BigIntegerField — no FloatField, no DecimalField",
    "balance_derivation": "DB aggregation only. Never fetch rows and sum in Python.",
    "balance_query_pattern": "Transaction.objects.filter(merchant=m).aggregate(balance=Sum(Case(When(type='credit', then=F('amount_paise')), When(type='debit', then=-F('amount_paise')), default=Value(0))))",
    "ledger_pattern": "Immutable append-only. Never mutate a balance field. Balance = derived from transaction history. Enables full audit trail and correct point-in-time balance.",
    "entities": {
      "Merchant": "id, name, bank_accounts[]",
      "Transaction": "id, merchant_id, type[credit|debit], amount_paise, payout_id (nullable), created_at",
      "BankAccount": "id, merchant_id, account_number, ifsc, label",
      "Payout": {
        "fields": "id, merchant_id, amount_paise, bank_account_id, status, idempotency_key, attempt_count, last_attempted_at, created_at, updated_at",
        "status_enum": ["pending", "processing", "completed", "failed"]
      },
      "IdempotencyRecord": "id, merchant_id, idempotency_key, response_status_code, response_body_json, created_at, expires_at"
    },
    "balance_split": {
      "available_paise": "SUM(credits) - SUM(debits where payout.status in [completed, failed, or no payout])",
      "held_paise": "SUM(debits where payout.status in [pending, processing])",
      "note": "A pending/processing payout creates a debit transaction immediately — this IS the hold mechanism"
    }
  },

  "api": {
    "POST /api/v1/payouts": {
      "headers": {
        "Idempotency-Key": "UUID, merchant-scoped, 24h TTL — required"
      },
      "body": {
        "amount_paise": "int > 0",
        "bank_account_id": "uuid"
      },
      "execution_order": [
        "1. Check IdempotencyRecord(merchant_id, key) — if exists and not expired, return stored response immediately",
        "2. Open atomic transaction",
        "3. SELECT FOR UPDATE on Merchant row (or balance anchor row)",
        "4. Compute available_balance via DB aggregation inside the lock",
        "5. If available_balance < amount_paise → 422, no payout created",
        "6. INSERT Payout(status=pending)",
        "7. INSERT Transaction(type=debit, payout_id=payout.id) — this holds the funds",
        "8. INSERT IdempotencyRecord with response snapshot",
        "9. Commit",
        "10. Enqueue background worker task(payout_id)",
        "11. Return 201 + payout object"
      ],
      "on_duplicate_key": "Return stored HTTP status + body snapshot. No new payout. No new transaction.",
      "on_insufficient_funds": "422 with clear message",
      "race_note": "Steps 3–9 must be inside the same atomic block with the lock. This is the entire concurrency solution."
    },
    "GET /api/v1/merchants/{id}/balance": {
      "returns": {"available_paise": "int", "held_paise": "int", "total_credits_paise": "int"}
    },
    "GET /api/v1/payouts": {
      "returns": "paginated payout list with status, timestamps, amount"
    },
    "GET /api/v1/merchants/{id}/transactions": {
      "returns": "ledger history — credits and debits with context"
    }
  },

  "background_worker": {
    "task_signature": "process_payout(payout_id: uuid)",
    "trigger": "enqueued immediately after payout creation (step 10 above)",
    "execution_flow": [
      "1. Fetch payout — if not status=pending, abort (idempotent task entry)",
      "2. Atomic: UPDATE status=processing, last_attempted_at=now WHERE status=pending (conditional update)",
      "3. If rows_affected=0 → another worker claimed it, exit",
      "4. Simulate bank settlement: random(0,1) → <0.70 success, <0.90 fail, else hang",
      "5a. Success: atomic UPDATE status=completed WHERE status=processing",
      "5b. Fail: atomic block — UPDATE status=failed + INSERT Transaction(type=credit) to return funds",
      "5c. Hang: leave in processing — retry poller will handle"
    ],
    "retry_logic": {
      "detection": "Periodic task: find payouts WHERE status=processing AND last_attempted_at < now()-30s AND attempt_count < 3",
      "action": "Increment attempt_count, re-enqueue process_payout",
      "backoff": "exponential — delay = 2^attempt_count seconds (or Celery countdown)",
      "on_max_attempts": "atomic block: UPDATE status=failed WHERE status=processing + INSERT credit transaction to return funds"
    },
    "atomicity_rule": "Any state transition to 'failed' that returns funds MUST do both operations in one DB transaction. Never two separate commits."
  },

  "state_machine": {
    "legal_transitions": [
      "pending → processing",
      "processing → completed",
      "processing → failed"
    ],
    "illegal_transitions": [
      "completed → anything",
      "failed → completed",
      "any backward transition"
    ],
    "enforcement_pattern": "Conditional UPDATE: `UPDATE payouts SET status='completed' WHERE id=X AND status='processing'` — check cursor.rowcount == 1. If 0, raise InvalidStateTransition. Never use application-level if/else as the guard — the DB check IS the guard.",
    "django_pattern": "rows = Payout.objects.filter(id=payout_id, status='processing').update(status='completed') — assert rows == 1"
  },

  "concurrency": {
    "problem": "Merchant has 10000 paise. Two simultaneous requests for 6000 paise each. Exactly one succeeds.",
    "root_cause_of_bugs": "TOCTOU — fetch balance, check in Python, then update. The gap between check and update is the race window.",
    "solution": "SELECT FOR UPDATE inside atomic transaction. Serializes concurrent payout requests at the DB row level.",
    "django_code": "with transaction.atomic(): merchant = Merchant.objects.select_for_update().get(id=merchant_id) — then compute balance and deduct inside same atomic block",
    "test": "Two threads, simultaneous requests, shared merchant, insufficient balance for both — assert exactly 1 payout in DB, balance never goes negative"
  },

  "idempotency": {
    "key_scope": "Per merchant — (merchant_id, idempotency_key) is the uniqueness unit",
    "storage": "IdempotencyRecord table with UNIQUE constraint on (merchant_id, idempotency_key)",
    "ttl": "24 hours — records with expires_at < now() are treated as absent (key can be reused)",
    "in_flight_handling": "DB UNIQUE constraint prevents double-insert. Second concurrent request gets IntegrityError → return 409 or poll for completion. First request response is stored atomically with the payout.",
    "response_storage": "Serialize HTTP status_code + response body JSON into IdempotencyRecord at commit time",
    "test": "Call POST /payouts twice with same Idempotency-Key — assert 1 Payout in DB, both responses are byte-identical"
  },

  "frontend": {
    "pages": [
      "Dashboard — merchant selector (seed 2-3 merchants)",
      "Balance panel — available_paise, held_paise (labeled clearly)",
      "Transaction history — credits and debits, amounts in INR display (paise ÷ 100)",
      "Payout form — amount (INR input, converted to paise), bank account selector, submit",
      "Payout history table — id, amount, status, created_at, updated_at with LIVE status updates"
    ],
    "live_status": "Poll GET /api/v1/payouts every 3-5s or use WebSocket. Status must update without page refresh.",
    "display_note": "Show amounts in ₹ (INR) with 2 decimal places in UI, store and compute in paise internally.",
    "strategic_touch": "Surface the USD→INR story somewhere — even a label like 'Collected in USD · Paid out in INR' signals you understand Playto's actual business."
  },

  "optional_bonuses": {
    "docker_compose": {
      "priority": "HIGH — do this first among bonuses",
      "reason": "One command to run everything signals production thinking. Shows you consider ops, not just dev."
    },
    "audit_log": {
      "priority": "MEDIUM",
      "reason": "Reinforces money integrity story. Every payout state change logged immutably."
    },
    "webhook_delivery": {
      "priority": "MEDIUM",
      "reason": "Realistic for payment systems. Merchants need to be notified of payout outcomes."
    },
    "event_sourcing": {
      "priority": "LOW",
      "reason": "Overkill for this scope. Ledger pattern already gives you immutable history."
    }
  },

  "explainer_md": {
    "priority": "CRITICAL — CTO reads this to decide if you understand your own code",
    "format": "Short and specific. Paste actual code, not pseudocode. Explain WHY not WHAT.",
    "questions": {
      "Q1_ledger": {
        "ask": "Paste the balance calculation query. Why are credits and debits modeled this way?",
        "answer_core": "Immutable ledger: never mutate a balance field. Append credits and debits as transactions. Balance = SUM aggregation at query time. This gives a full audit trail, correct historical balance, and eliminates update conflicts on a single balance row."
      },
      "Q2_lock": {
        "ask": "Paste the exact code preventing concurrent overdraw. What DB primitive?",
        "answer_core": "SELECT FOR UPDATE — acquires an exclusive row-level lock. All concurrent transactions trying to modify the same merchant row queue behind it. The check-and-deduct happen inside the same locked transaction, eliminating the TOCTOU window entirely."
      },
      "Q3_idempotency": {
        "ask": "How does the system know it has seen a key before? What if the first request is still in flight?",
        "answer_core": "UNIQUE(merchant_id, idempotency_key) DB constraint. First INSERT wins. Second INSERT raises IntegrityError — we return the stored response. In-flight: the constraint still blocks the second insert. We return 409 or a polling response. The stored response is written atomically with the payout commit, so we never store a response for a failed transaction."
      },
      "Q4_state_machine": {
        "ask": "Where in the code is failed→completed blocked? Show the check.",
        "answer_core": "Conditional UPDATE: `Payout.objects.filter(id=X, status='processing').update(status='completed')` — if rows_affected == 0, the guard failed. We raise InvalidStateTransition. There is no application-level if/else. The WHERE clause IS the guard — it's enforced by the DB, not the application."
      },
      "Q5_ai_audit": {
        "ask": "One specific example where AI wrote subtly wrong code. Paste what it gave, what you caught, and what replaced it.",
        "prep_note": "Have a real example. Common AI mistakes: (1) computing balance with payout = Merchant.objects.get().balance then checking balance >= amount — race window wide open; (2) F() expressions outside atomic blocks; (3) doing fund return in a separate transaction from state update. Catch one of these, document it."
      }
    }
  },

  "implementation_constraints": {
    "must_implement": [
      "paise integers only — BigIntegerField, no float math anywhere in the codebase",
      "balance via DB aggregation — never Python sum() on fetched rows",
      "SELECT FOR UPDATE inside atomic() for the entire payout creation flow",
      "idempotency via DB UNIQUE constraint — not application-level 'check before insert'",
      "state transitions via conditional UPDATE — verify rows_affected == 1",
      "fund return on failure inside same DB transaction as status=failed update",
      "real async worker — Celery/Django-Q/Huey running in a separate process"
    ],
    "required_tests": [
      "concurrency: two threads simultaneously POST /payouts with same merchant, balance < sum of requests — assert exactly 1 succeeds, 1 rejects, balance never negative",
      "idempotency: POST /payouts twice with same Idempotency-Key — assert 1 Payout row in DB, both HTTP responses identical"
    ],
    "seed_requirements": "Management command or fixture. 2-3 merchants, each with: 2-3 credit transactions, 1-2 bank accounts, mixed payout history. One command to run."
  },

  "strategic_differentiation": {
    "what_they_actually_grade": [
      "Ledger model correctness — do you know that balance is a derived aggregate, not a stored field?",
      "Concurrency correctness — do you know SELECT FOR UPDATE vs application-level locking?",
      "Idempotency implementation — DB constraint vs naive check, in-flight handling",
      "State machine enforcement — DB-level guards vs application if/else",
      "EXPLAINER quality — precise, code-backed, no hand-waving"
    ],
    "what_they_dont_grade": [
      "Pixel-perfect UI",
      "Full test coverage",
      "Fancy patterns",
      "Features beyond the spec"
    ],
    "stand_out_signal": "Show you understand what Playto is building: an INR payout engine that holds USD float and settles to Indian bank accounts. This challenge is literally their core infrastructure. Build it like you're shipping it, not demoing it. The EXPLAINER is where you prove you're the engineer they've been looking for.",
    "commit_history_note": "Clean semantic commits tell a story. Show progression of thinking — not a single 'initial commit' dump."
  }
}
```
