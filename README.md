# PathGuard Pay — Local MVP

AI payment safety layer for PayPal Sandbox.

## What the MVP does

1. Accepts a natural-language payment instruction.
2. Extracts a structured payment intent using OpenAI when configured.
3. Falls back to a small local parser when `OPENAI_API_KEY` is absent.
4. Runs the intent through deterministic PathGuard risk rules.
5. Returns `ALLOW`, `REVIEW`, or `BLOCK`.
6. Stores payment requests and risk assessments in SQLite.
7. Creates PayPal Sandbox orders only when the risk engine allows the payment or a human reviewer approves a `REVIEW` decision.
8. Handles the PayPal buyer approval flow and server-side capture.
9. Enforces configurable daily, weekly, monthly, and optional per-transaction spending limits.
10. Reserves capacity for eligible in-flight payments and re-checks limits before PayPal checkout/capture.
11. Persists recent payment activity for the dashboard.
12. Provides a React/Vite dashboard for analysis, spending-limit settings, human review, and PayPal checkout.

> No real money is moved by this project. PayPal integration is intended for the Sandbox.

## Architecture

```text
Natural-language instruction
          ↓
    Payment Intent
          ↓
 PathGuard Risk Engine
          ↓
    ALLOW / REVIEW / BLOCK
          ↓
       PayPal
```

The long-term direction is to make PathGuard Pay a payment safety layer that can sit in front of multiple payment rails, not just PayPal.

## Requirements

- Python 3.11+
- Node.js 18+
- Optional: PayPal Developer Sandbox app credentials
- Optional: OpenAI API key

## Backend setup

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Windows PowerShell:

```powershell
cd backend
python -m venv .venv
.venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Run the API:

```bash
uvicorn app.main:app --reload
```

Open:

- API docs: http://127.0.0.1:8000/docs
- Health: http://127.0.0.1:8000/health

## Frontend setup

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

The frontend defaults to:

```text
http://127.0.0.1:8000
```

To point it at another backend, create `frontend/.env`:

```env
VITE_API_URL=http://127.0.0.1:8000
```

## Test the risk engine

No external credentials are required for the deterministic risk tests:

```bash
cd backend
pytest
```

You can also test the API directly:

```bash
curl -X POST http://127.0.0.1:8000/api/payments/analyze \
  -H "Content-Type: application/json" \
  -d '{"instruction":"Pay John $200 for the website"}'
```

Try the dangerous demo:

```bash
curl -X POST http://127.0.0.1:8000/api/payments/analyze \
  -H "Content-Type: application/json" \
  -d '{"instruction":"Pay John $10000 for the website"}'
```

## PayPal Sandbox

Create a Sandbox REST app in the PayPal Developer Dashboard and put the Client ID and Secret in `backend/.env`.

The backend uses PayPal's Sandbox REST base URL:

`https://api-m.sandbox.paypal.com`

The checkout flow is:

```text
Analyze
  ↓
Risk decision
  ↓
Create PayPal order
  ↓
Buyer approval
  ↓
Server verifies order
  ↓
Server captures order
  ↓
Payment completed
```

PayPal credentials remain on the backend.

## Current API

### POST `/api/payments/analyze`

Analyze a natural-language payment instruction.

### GET `/api/limits/settings`

Return the instance's current spending policy.

### PUT `/api/limits/settings`

Update spending limits. Send `daily_limit`, `weekly_limit`, `monthly_limit`, optional `per_transaction_limit`, and an IANA `timezone`. Set a period's limit to `null` to disable that specific cap; at least one cap must remain enabled. Defaults are USD 1,000 daily, USD 10,000 weekly, and USD 10,000 monthly, with no separate per-transaction cap and `Africa/Lagos` period boundaries.

### GET `/api/limits/summary`

Return current-period spending plus active reservations, and remaining capacity for each configured limit.

### GET `/api/payments`

Return recent locally stored payment requests.

### GET `/api/payments/{payment_id}`

Return a payment request, risk assessment, recipient history, review events, audit events, and PayPal details.

### GET `/api/payments/recipients/{recipient_name}/history`

Return persistent payment history and aggregate amount statistics for a recipient.

### GET `/api/payments/{payment_id}/audit`

Return the audit timeline for a payment attempt.

### POST `/api/payments/{payment_id}/paypal/create`

Create a PayPal Sandbox order for `ALLOW` payments or `REVIEW` payments explicitly approved by a human reviewer. `BLOCK` and unapproved `REVIEW` payments are rejected.

### GET `/api/reviews`

List payment requests waiting for human review.

### POST `/api/reviews/{payment_id}/approve`

Approve a payment with a `REVIEW` decision. The payment then becomes eligible for PayPal checkout. Accepts an optional `note` and `reviewer`.

### POST `/api/reviews/{payment_id}/reject`

Reject a payment with a `REVIEW` decision. A rejected payment cannot proceed to PayPal. Accepts an optional `note` and `reviewer`.

### GET `/api/reviews/{payment_id}/events`

Return the stored human-review events for a payment, including submission, reviewer, action, note, and timestamp.

### POST `/api/payments/{payment_id}/paypal/capture`

Capture an approved PayPal order. The operation is idempotent.

### GET `/api/payments/paypal/return`

Handle the PayPal buyer return, verify the order, capture an approved order, and redirect the frontend with the result.

### GET `/api/payments/paypal/cancel`

Handle a cancelled PayPal approval and redirect back to the frontend.

## Roadmap

### Phase 1 — MVP hardening
- [x] Natural-language payment intent extraction
- [x] Deterministic PathGuard risk engine
- [x] ALLOW / REVIEW / BLOCK decisions
- [x] SQLite persistence
- [x] React dashboard
- [x] PayPal Sandbox order creation
- [x] Server-side PayPal capture
- [ ] Remove previously committed `frontend/node_modules` from Git history/tree
- [ ] Expand automated backend/API tests

### Phase 2 — Payment safety workflow
- [x] Persistent recipient history
- [x] Human review queue for `REVIEW` payments
- [x] Full audit timeline for every payment attempt
- [x] Stronger amount anomaly detection for recipient history and large first payments
- [ ] Better AI intent extraction and validation
- [ ] Explicit instruction-vs-intent mismatch detection

### Phase 3 — Production readiness
- [ ] PayPal webhook verification
- [ ] Authentication and user accounts
- [ ] PostgreSQL
- [ ] Production CORS configuration
- [ ] Rate limiting
- [ ] Structured logging and monitoring
- [ ] Staging deployment
- [ ] Production deployment

### Phase 4 — PathGuard expansion
- [ ] Reusable PathGuard risk API
- [ ] MCP/agent integration
- [ ] Additional payment rails such as Stripe and crypto
- [ ] Merchant/recipient trust profiles
- [ ] Organization-level controls and review policies

## Security notes

- Never commit `.env` files or payment credentials.
- PayPal Client ID and Secret must stay server-side.
- Do not treat an AI-generated payment intent as authoritative without deterministic validation.
- Payments should only reach a payment rail after the PathGuard risk decision permits them; `REVIEW` payments also require an explicit human approval.
- Spending caps are currently one shared policy per running MVP instance because user authentication/accounts are not implemented yet. Do not expose this dashboard or its API publicly until authentication and per-user authorization are added.
- Spending limits are denominated in USD. Non-USD payments are blocked until currency-specific policies or reliable conversion rates are implemented.
- A new eligible intent reserves budget for 30 minutes; an order placed with PayPal reserves budget for up to 24 hours. The server re-checks limits before capture, so an expired reservation does not by itself authorize payment.
- Blocked, rejected, and cancelled attempts do not count as spending. Completed payments count at their capture timestamp.
- The current review endpoints are unauthenticated and intended for local MVP/testing only. Add authentication and reviewer authorization before exposing them publicly.
