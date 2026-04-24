# Software Requirements Specification — Playto Payout Engine

> Built strictly from the content of the "Playto Founding Engineer Challenge 2026" page. Nothing is added that is not in the source.

---

## 1. Project Context

### 1.1 About Playto Pay
Cross-border payment infrastructure for Indian agencies, freelancers, and online businesses who cannot access Stripe or PayPal. Positioned as the Mercury-equivalent for emerging market businesses.

Reference: `playto.so/features/playto-pay`

### 1.2 Domain
Playto Pay helps Indian agencies and freelancers collect international payments. Money flows in one direction:

- International customer pays in **USD**
- Playto collects
- Playto pays merchant in **INR**

The hardest part is not payment collection — it is the **payout engine** that sits in the middle. Merchants accumulate balance when their customers pay, and they withdraw to their Indian bank account. This challenge is to build a minimal version of that engine.

### 1.3 Role / Engagement (context only)
- Role: Founding Engineer. Full-time, Remote, India.
- Compensation: 6–10 LPA Fixed plus ESOPs.
- Deadline: 5 days from receiving the task.
- Expected effort: 10 to 15 hours of focused work.

---

## 2. Goal

Build a service where merchants can:

1. See their balance.
2. Request payouts.
3. Track payout status.

The service must handle the **concurrency, idempotency, and data integrity** problems that real payment systems fail at.

---

## 3. Tech Stack (Required)

| Layer | Required |
|---|---|
| Backend | Django + DRF |
| Frontend | React + Tailwind |
| Database | PostgreSQL (strongly preferred) |
| Background jobs | Celery, Django-Q, or Huey |

Constraint: **Do not fake background jobs with sync code.**

---

## 4. Functional Requirements

### FR-1. Merchant Ledger
- Every merchant has a balance in **paise**, stored as an **integer**. Never floats.
- Balance is **derived** from:
  - **credits** — simulated customer payments
  - **debits** — payouts
- Seed **2 to 3 merchants** with credit history.
- The customer payment flow does **not** need to be built.

### FR-2. Payout Request API
- Endpoint: `POST /api/v1/payouts`
- Header: idempotency key
- Body fields:
  - `amount_paise`
  - `bank_account_id`
- Behavior:
  - Creates a payout in `pending` state.
  - **Holds the funds.**
  - If called twice with the same idempotency key, returns the **same response** as the first call.

### FR-3. Payout Processor (Background Worker)
- Picks up `pending` payouts and moves them through the lifecycle.
- Simulated bank settlement outcomes:
  - **70%** succeed
  - **20%** fail
  - **10%** hang in `processing`
- On **success** — payout is final.
- On **failure** — held funds return to merchant balance.

### FR-4. Merchant Dashboard (React)
Must show:
- Available balance
- Held balance
- Recent credits and debits
- Form to request a payout
- Table of payout history with **live status updates**

---

## 5. Technical Constraints (Graded)

> "These are the parts we actually grade you on. Features are easy. These are not."

### TC-1. Money Integrity
- Amounts stored as `BigIntegerField` in paise.
- No `FloatField`.
- No `DecimalField` unless there is a good reason.
- Balance calculations must use **database-level operations**, not Python arithmetic on fetched rows.
- **Invariant (checked):** sum of credits − debits must always equal the displayed balance.

### TC-2. Concurrency
- Scenario: a merchant with ₹100 balance submits two simultaneous ₹60 payout requests.
- **Exactly one** must succeed.
- The other must be **rejected cleanly**.
- Note: race conditions on check-then-deduct are the most common bug.

### TC-3. Idempotency
- `Idempotency-Key` header is a merchant-supplied UUID.
- Second call with the same key returns the **exact same response** as the first.
- **No duplicate payout** created.
- Keys are **scoped per merchant**.
- Keys **expire after 24 hours**.

### TC-4. State Machine
- Legal transitions:
  - `pending → processing → completed`
  - `pending → processing → failed`
- Illegal (must be rejected):
  - `completed → pending`
  - `failed → completed`
  - Any backwards transition
- A `failed` payout returning funds must do so **atomically** with the state transition.

### TC-5. Retry Logic
- Payouts stuck in `processing` for **more than 30 seconds** are retried.
- **Exponential backoff.**
- **Max 3 attempts**, then move to `failed` and return funds.

---

## 6. AI Policy

- AI-native, not AI-dependent.
- Must be able to explain every line.
- Must catch where AI gave wrong code, especially around **transactions, locking, and aggregation**.
- `EXPLAINER.md` is how it is determined whether code is understood or pasted.
- Use of any AI tool is allowed. Quality of thinking is graded, not typing speed.

---

## 7. Deliverables

### 7.1 Repository
- GitHub repository with all code and **clean commit history**.
- `README.md` with setup instructions.
- **Seed script** to populate merchants.
- At least **2 meaningful tests**:
  - one for **concurrency**
  - one for **idempotency**

### 7.2 Live Deployment
- Deployed on any free provider: Railway, Render, Fly.io, Vercel, Koyeb.
- URL shared via the submission form.
- Seeded with test data.

### 7.3 EXPLAINER.md
Answer the following — short and specific:

1. **The Ledger** — Paste the balance calculation query. Why credits and debits modeled this way?
2. **The Lock** — Paste the exact code that prevents two concurrent payouts from overdrawing a balance. Explain what database primitive it relies on.
3. **The Idempotency** — How does the system know it has seen a key before? What happens if the first request is in flight when the second arrives?
4. **The State Machine** — Where in the code is `failed → completed` blocked? Show the check.
5. **The AI Audit** — One specific example where AI wrote subtly wrong code (bad locking, wrong aggregation, race condition). Paste what it gave, what was caught, and what replaced it.

### 7.4 Optional Bonuses
Pick only those of interest — do **not** do all:
- `docker-compose.yml`
- Event sourcing
- Webhook delivery with retries
- Audit log

---

## 8. Evaluation Criteria

Graded on:
- **Clean ledger model** — signals ownership of money-moving systems.
- **Correct concurrency handling** — signals understanding of Python-level vs database-level locking.
- **Good idempotency implementation** — signals having shipped APIs that deal with real networks.
- **Sharp EXPLAINER.md** — signals understanding own code; not freezing in a debugging call.
- **Honest AI audit** — signals seniority; not blindly trusting the machine.

NOT graded on:
- Pixel-perfect UI
- Perfect test coverage
- Fancy patterns
- Feature completeness beyond what is listed

Additional notes from the brief:
- Not looking for a perfect submission.
- Looking for someone who thinks like an engineer shipping money-moving code to production.
- Architecture decisions matter more than polish.
- Correctness matters more than features.

---

## 9. Process After Submission

1. CTO reviews the code and EXPLAINER in 1–2 days.
2. If shortlisted: 45-minute technical conversation with CTO.
3. Final 30-minute chat with CEO.
4. Offer within 48 hours of the final chat.

---

## 10. Submission

- Submission via the provided form.
- Form asks for:
  - GitHub repo link
  - Hosted deployment URL
  - Short note on what you are most proud of
- Questions: email `sanhik@playto.so`. Do **not** DM on LinkedIn or Instagram.
- WhatsApp Community link is provided for further updates.

---

## 11. Deadline

- **5 days** from email receipt.
- **Late submissions will not be reviewed.**
