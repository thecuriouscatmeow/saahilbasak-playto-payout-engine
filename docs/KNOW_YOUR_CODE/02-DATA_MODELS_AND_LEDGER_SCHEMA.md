# 02-DATA_MODELS_AND_LEDGER_SCHEMA

## Persistence Shape
The data model is centered on a merchant-scoped ledger rather than a mutable balance table. `Merchant` owns `BankAccount`; `Payout` links merchant to bank account and carries lifecycle state; `Transaction` is the financial truth source; `PayoutEvent` records status transitions; `IdempotencyRecord` stores request dedupe state and replay bodies. Evidence: `backend/apps/merchants/models.py`, `backend/apps/payouts/models.py`.

## Core Models
### Merchant
- Fields: `id`, `name`, `created_at`. Evidence: `backend/apps/merchants/models.py::Merchant`.
- Table: `merchants`. Evidence: `backend/apps/merchants/models.py::Merchant.Meta`.
- Role: merchant identity root for bank accounts, payouts, transactions, and idempotency records. Evidence: `backend/apps/merchants/models.py::Merchant`, `backend/apps/payouts/models.py::Payout`, `backend/apps/payouts/models.py::Transaction`, `backend/apps/payouts/models.py::IdempotencyRecord`.

### BankAccount
- Fields: `id`, `merchant`, `ifsc`, `account_number`, `label`, `is_active`, `created_at`. Evidence: `backend/apps/merchants/models.py::BankAccount`.
- Relationship: many bank accounts per merchant via `related_name="bank_accounts"`. Evidence: `backend/apps/merchants/models.py::BankAccount`.
- Table: `bank_accounts`. Evidence: `backend/apps/merchants/models.py::BankAccount.Meta`.
- Operational use: payout creation only accepts accounts matching merchant and `is_active=True`. Evidence: `backend/apps/payouts/services/create_payout.py::CreatePayoutService._run_critical_path`.

### Payout
- Fields: `id`, `merchant`, `bank_account`, `amount_paise`, `status`, `last_attempted_at`, `attempts`, `created_at`, `updated_at`. Evidence: `backend/apps/payouts/models.py::Payout`.
- Table: `payouts`. Evidence: `backend/apps/payouts/models.py::Payout.Meta`.
- Constraints:
  - `amount_paise > 0`. Evidence: `backend/apps/payouts/models.py::Payout.Meta`, `backend/tests/integration/test_db_constraints.py::test_payout_negative_amount_rejected`.
  - `status` must be one of enum values. Evidence: `backend/apps/payouts/models.py::Payout.Meta`, `backend/apps/payouts/domain/enums.py::PayoutStatus`.
- Indexes:
  - `(merchant, -created_at)` for merchant history views. Evidence: `backend/apps/payouts/models.py::Payout.Meta`.
  - Partial index on `(status, last_attempted_at)` for `processing` payouts, used by stale sweep logic. Evidence: `backend/apps/payouts/models.py::Payout.Meta`.
- Lifecycle:
  - Starts `pending`. Evidence: `backend/apps/payouts/repositories/payout_repo.py::create_with_hold`.
  - Can transition only `pending -> processing -> completed|failed`. Evidence: `backend/apps/payouts/domain/transitions.py::LEGAL`, `backend/apps/payouts/repositories/payout_repo.py::transition`.

### Transaction
- Fields: `id`, `merchant`, `payout`, `type`, `amount_paise`, `created_at`. Evidence: `backend/apps/payouts/models.py::Transaction`.
- Table: `transactions`. Evidence: `backend/apps/payouts/models.py::Transaction.Meta`.
- Constraints:
  - `amount_paise > 0`. Evidence: `backend/apps/payouts/models.py::Transaction.Meta`, `backend/tests/integration/test_db_constraints.py::test_transaction_negative_amount_rejected`.
  - `type` must be one of `credit`, `hold`, `release`, `debit`. Evidence: `backend/apps/payouts/models.py::Transaction.Meta`, `backend/apps/payouts/domain/enums.py::TxnType`, `backend/tests/integration/test_db_constraints.py::test_transaction_invalid_type_rejected`.
  - `credit` must have no payout; `hold`, `release`, and `debit` must have a payout. Evidence: `backend/apps/payouts/models.py::Transaction.Meta`, `backend/tests/integration/test_db_constraints.py::test_credit_with_payout_rejected`, `backend/tests/integration/test_db_constraints.py::test_hold_without_payout_rejected`.
- Indexes:
  - `(merchant, -created_at)` for merchant ledger views. Evidence: `backend/apps/payouts/models.py::Transaction.Meta`.
  - `(payout)` for payout-linked transaction inspection. Evidence: `backend/apps/payouts/models.py::Transaction.Meta`.

### PayoutEvent
- Fields: `id`, `payout`, `from_status`, `to_status`, `note`, `created_at`. Evidence: `backend/apps/payouts/models.py::PayoutEvent`.
- Table: `payout_events`. Evidence: `backend/apps/payouts/models.py::PayoutEvent.Meta`.
- Index: `(payout, created_at)`. Evidence: `backend/apps/payouts/models.py::PayoutEvent.Meta`.
- Source of truth: appended through `event_repo.append()` during `payout_repo.transition()`. Evidence: `backend/apps/payouts/repositories/event_repo.py::append`, `backend/apps/payouts/repositories/payout_repo.py::transition`.

### IdempotencyRecord
- Fields: `id`, `merchant`, `idempotency_key`, `request_hash`, `state`, `payout`, `response_body`, `expires_at`, `created_at`, `updated_at`. Evidence: `backend/apps/payouts/models.py::IdempotencyRecord`.
- Table: `idempotency_records`. Evidence: `backend/apps/payouts/models.py::IdempotencyRecord.Meta`.
- Constraints:
  - Unique `(merchant, idempotency_key)`. Evidence: `backend/apps/payouts/models.py::IdempotencyRecord.Meta`, `backend/tests/integration/test_db_constraints.py::test_idempotency_unique_key_constraint`.
  - `state` must be `in_flight` or `completed`. Evidence: `backend/apps/payouts/models.py::IdempotencyRecord.Meta`, `backend/apps/payouts/domain/enums.py::IdempotencyState`.
- Index:
  - `(expires_at)` for purge scans. Evidence: `backend/apps/payouts/models.py::IdempotencyRecord.Meta`, `backend/apps/payouts/repositories/idempotency_repo.py::purge_expired`.

## Relationship Map
- One `Merchant` has many `BankAccount`s. Evidence: `backend/apps/merchants/models.py::BankAccount`.
- One `Merchant` has many `Payout`s, `Transaction`s, and `IdempotencyRecord`s through foreign keys. Evidence: `backend/apps/payouts/models.py::Payout`, `backend/apps/payouts/models.py::Transaction`, `backend/apps/payouts/models.py::IdempotencyRecord`.
- One `Payout` can have many `Transaction`s over time and many `PayoutEvent`s. Evidence: `backend/apps/payouts/models.py::Transaction`, `backend/apps/payouts/models.py::PayoutEvent`.

## Ledger Truth Model
The repo computes balance from transaction aggregates instead of storing a mutable balance field on `Merchant`. That is not a design rumor; `get_balance_breakdown()` aggregates four transaction types and returns `available_paise`, `held_paise`, and `total_credits_paise`. Evidence: `backend/apps/payouts/repositories/merchant_repo.py::get_balance_breakdown`.

### Formula
```text
available = credits - holds + releases - debits
held = holds - releases - debits
total_credits = credits
```
Evidence: `backend/apps/payouts/repositories/merchant_repo.py::get_balance_breakdown`.

### Transaction Type Semantics
- `credit`: inflow funding the merchant ledger. Evidence: `backend/apps/payouts/repositories/transaction_repo.py::insert_credit`.
- `hold`: reservation created together with a payout in `pending`. Evidence: `backend/apps/payouts/repositories/payout_repo.py::create_with_hold`, `backend/apps/payouts/repositories/transaction_repo.py::insert_hold`.
- `release`: restoration of held funds when a payout fails or max-attempt retries are exhausted. Evidence: `backend/apps/payouts/repositories/transaction_repo.py::insert_release`, `backend/apps/payouts/services/process_payout.py::ProcessPayoutService.execute`, `backend/apps/payouts/services/retry_stale.py::RetryStalePayoutsService._handle_stale`.
- `debit`: finalization of an outgoing payout after successful settlement. Evidence: `backend/apps/payouts/repositories/transaction_repo.py::insert_debit`, `backend/apps/payouts/services/process_payout.py::ProcessPayoutService.execute`.

### Worked Examples
- Success path: credit `50_000`, hold `20_000`, debit `20_000` yields available `10_000` and held `0`. Evidence: `backend/tests/integration/test_worker_success.py::test_success_path`.
- Failure path: credit `50_000`, hold `20_000`, release `20_000` yields available `50_000` and held `0`. Evidence: `backend/tests/integration/test_worker_failure_refund.py::test_failure_atomically_releases`.
- Concurrency path: five successful `hold` reservations of `6_000` against `30_000` total credit leaves available `0` and held `30_000`. Evidence: `backend/tests/integration/test_concurrency_tier2.py::test_concurrency_tier2`.

## Lifecycle Timestamps
- `Merchant` and `BankAccount` only record creation time. Evidence: `backend/apps/merchants/models.py`.
- `Payout` records `created_at`, `updated_at`, and optionally `last_attempted_at`. Evidence: `backend/apps/payouts/models.py::Payout`.
- `Transaction` and `PayoutEvent` are append-timestamped only. Evidence: `backend/apps/payouts/models.py::Transaction`, `backend/apps/payouts/models.py::PayoutEvent`.
- `IdempotencyRecord` records creation and update times plus `expires_at`, which is operationally significant for replay eligibility and purge. Evidence: `backend/apps/payouts/models.py::IdempotencyRecord`, `backend/apps/payouts/services/create_payout.py::CreatePayoutService.IDEMPOTENCY_TTL_HOURS`.

## State and Reconciliation Invariants
The legal payout state machine is deliberately narrow: there is no direct `pending -> completed`, `pending -> failed`, or terminal-to-terminal hop. Evidence: `backend/apps/payouts/domain/transitions.py::LEGAL`, `backend/tests/unit/test_domain_transitions.py`.

The reconciliation service codifies the ledger invariants the schema alone cannot enforce:
- held ledger balance should equal total amounts for payouts still in `pending` or `processing`
- terminal payouts should have exactly one hold and exactly one terminal offset transaction
- a payout should never have both debit and release
Evidence: `backend/apps/payouts/services/reconcile_ledger.py::ReconcileLedgerService._check_merchant`, `backend/tests/integration/test_reconciliation.py::test_reconcile_clean_after_completed_payout`, `backend/tests/integration/test_reconciliation.py::test_reconcile_detects_orphan_release`.

## Money Representation
Money is stored as integer paise, not floating point. Model fields use `BigIntegerField` for `amount_paise`, and helper functions convert rupees to paise with `Decimal` before casting to int. Evidence: `backend/apps/payouts/models.py::Payout`, `backend/apps/payouts/models.py::Transaction`, `backend/apps/payouts/domain/money.py::rupees_to_paise`, `backend/apps/payouts/domain/money.py::paise_to_rupees`.

This avoids floating-point drift in persisted values, although frontend form parsing still begins with `parseFloat()` before rounding to paise. Evidence: `frontend/src/features/PayoutForm.tsx::handleSubmit`. That is acceptable for two-decimal UI entry but worth remembering during UX changes.

## Dangerous Hardcoded Values
- Idempotency TTL is fixed at 24 hours in application code, not settings. Evidence: `backend/apps/payouts/services/create_payout.py::CreatePayoutService.IDEMPOTENCY_TTL_HOURS`.
- Stale retry maximum attempts is fixed at 3 in service code. Evidence: `backend/apps/payouts/services/retry_stale.py::MAX_ATTEMPTS`.
- Default stale threshold is 30 seconds and stale sweep SQL default limit is 100 rows. Evidence: `backend/apps/payouts/services/retry_stale.py::RetryStalePayoutsService.__init__`, `backend/apps/payouts/repositories/payout_repo.py::claim_stale_with_skip_locked`.

## Known Unknowns
- There is only one migration snapshot in repo, and no later schema evolution trail. That means schema intent is clear for the current snapshot but long-term compatibility history is not. Evidence: `backend/apps/merchants/migrations/0001_initial.py`, `backend/apps/payouts/migrations/0001_initial.py`. Confidence: Medium.
- The ledger is append-oriented in practice, but the code does not enforce full immutability beyond "no update helpers exist here." Admin tooling or ad hoc SQL outside the repo could still mutate rows. Evidence: absence of transaction update functions in `backend/apps/payouts/repositories/transaction_repo.py`. Confidence: Medium.
- There is no explicit foreign-key uniqueness preventing multiple payouts from sharing the same bank account, which is probably intentional but not spelled out in docs or comments. Evidence: `backend/apps/payouts/models.py::Payout`, `backend/apps/merchants/models.py::BankAccount`. Confidence: Medium.
- The balance formula assumes transaction rows remain semantically consistent; the schema cannot prove "one hold per payout before terminalization" by itself, so reconciliation is the real safety net. Evidence: `backend/apps/payouts/services/reconcile_ledger.py::ReconcileLedgerService`. Confidence: High.
