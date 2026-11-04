# PathGuard Pay

Check first. Pay second.

PathGuard Pay lets you describe a payment in your own words, check the details, and continue to PayPal when you're ready. It looks at the amount, your payment history, and your spending limits to decide whether a request can go ahead, needs your confirmation, or should be stopped.

[Open PathGuard Pay](https://pathguard-pay.onrender.com) · [Explore PathGuard](https://pathguard.cieltech.org/) · [Deployment guide](docs/render-deployment.md)

**The app currently uses PayPal Sandbox. No real money is moved.**

## Why we built it

A payment can look ordinary until you notice an extra zero, an unfamiliar recipient, or an amount that is much higher than usual. We wanted a place to catch those details before opening checkout.

PathGuard Pay puts that check between the instruction and the payment. You can see what the app understood, why it flagged something, and what needs to happen next.

## Try it

1. Create an account or sign in.
2. Open **New payment** and enter something like “Pay John $12 for a logo.”
3. Check the recipient, amount, purpose, and safety result.
4. If the request needs review, open **Payment reviews**. You can reject it or confirm it by entering your account password again.
5. Continue to PayPal using a Sandbox buyer account.
6. Open **Transactions** to check the payment status. Click a transaction to view and copy its PayPal Order ID and Capture ID, when available.

The three results are:

| Result | What happens |
|---|---|
| `ALLOW` | The request passes the current checks and can continue to checkout. |
| `REVIEW` | Checkout waits for an explicit confirmation or an authorized staff review. |
| `BLOCK` | The request cannot continue to checkout. |

Passing a check does not verify a recipient's identity or guarantee that a payment is safe.

## What's included

- **Payment instructions in plain language.** OpenRouter extracts the recipient, amount, currency, and purpose. A local parser handles simpler instructions when no API key is configured.
- **Checks before checkout.** The app looks for new recipients, unusual amounts, changes in payment purpose, repeated completed payments, and spending-limit breaches.
- **Spending controls.** Set daily, weekly, monthly, and optional per-payment limits, with a timezone for resets. Eligible requests reserve budget while checkout is in progress.
- **PayPal checkout.** Sandbox order creation, buyer approval, server-side verification, and capture. Saved-wallet support is available through PayPal Vault when enabled.
- **Payment records.** Account-specific history, review records, audit events, and copyable PayPal references.
- **Insights and notifications.** Payment totals, recurring error signals, in-app updates, and optional AI summaries.
- **Administration.** Role-protected user management, account controls, and payment monitoring.

The default limits are **$1,000 daily, $10,000 weekly, and $10,000 monthly**, using `Africa/Lagos` time. Users can change their limits in the app. Spending policies currently support USD; other currencies are blocked.

### Where AI fits

AI helps turn a written instruction into payment details and can summarize operational activity. The risk rules and spending limits run in the backend. An AI response cannot override a block, approve a review, or bypass a limit.

### A note about PayPal

This project uses PayPal Orders for checkout under the configured Sandbox merchant account. A name such as “John” is part of the payment request and its history; it does not route a payout to that person's PayPal account. Direct person-to-person payouts are not implemented.

Saving a wallet is optional. It requires Vault access in the PayPal Sandbox app. A saved wallet may be charged without a separate checkout approval each time, although PayPal can still require payer action. PathGuard's checks still apply.

## Run locally

You'll need Python 3.11 or later, Node.js 20 or later, npm, and Git. PayPal Sandbox credentials are needed to test checkout. An OpenRouter key is needed to use the AI features.

```bash
git clone https://github.com/Utee/pathguard-pay-mvp.git
cd pathguard-pay-mvp
```

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

On Windows PowerShell, activate the environment with `.venv\Scripts\Activate.ps1`.

Generate a signing key:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Put it in `JWT_SECRET_KEY` in `backend/.env`, then add the credentials you want to use:

| Variable | Used for |
|---|---|
| `JWT_SECRET_KEY` | Signing account access tokens. Required for registration and login. |
| `PAYPAL_CLIENT_ID` | Your PayPal Sandbox app's client ID. |
| `PAYPAL_CLIENT_SECRET` | Your PayPal Sandbox app's secret. |
| `OPENROUTER_API_KEY` | AI instruction parsing and summaries. |
| `OPENROUTER_MODEL` | The model to use. The example file includes a default. |
| `DATABASE_URL` | SQLite locally, or a PostgreSQL connection URL. |
| `PAYPAL_VAULT_ENCRYPTION_KEY` | Encrypting saved-wallet tokens, if you enable Vault. |

Keep the Sandbox API URL from `.env.example`. Don't commit your `.env` file or any credentials.

For saved wallets, generate an encryption key:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Set that value as `PAYPAL_VAULT_ENCRYPTION_KEY`. Keep it stable: replacing it makes previously saved tokens unreadable. Enable the necessary payment and Vault capabilities in your Sandbox REST app.

Start the API from the `backend` directory:

```bash
uvicorn app.main:app --reload
```

- API: http://127.0.0.1:8000
- Interactive API docs: http://127.0.0.1:8000/docs
- Health check: http://127.0.0.1:8000/health

The database tables are created on startup. A fresh database starts empty.

### Frontend

Open another terminal at the repository root:

```bash
cd frontend
npm ci
npm run dev
```

Open the address printed by Vite. The frontend uses `http://127.0.0.1:8000` by default. If your API runs elsewhere, set `VITE_API_URL` in `frontend/.env`. Add the frontend's exact origin to the backend's `CORS_ALLOWED_ORIGINS` setting.

Register through the app to create a customer account. For a reviewer or administrator, run this from `backend`:

```bash
python scripts/create_user.py staff@example.com --name "Staff Member" --role reviewer
```

Use `--role admin` for an administrator. The script prompts for a password; staff roles cannot be chosen through public registration.

## Hosting

The hosted app uses a Render static site, a FastAPI web service, and PostgreSQL. The root `render.yaml` describes that setup, including internal database access and the frontend/API connections.

See [the Render deployment guide](docs/render-deployment.md) for credentials, callback URLs, and verification steps. Applying the Blueprint creates paid resources. Moving from local SQLite to a new hosted database does not automatically move existing users or payment records.

## Checks

Run backend tests from `backend`:

```bash
python -m pytest -q
```

Build the frontend from `frontend`:

```bash
npm ci
npm run build
```

GitHub Actions runs the backend tests, a PostgreSQL persistence check, and the frontend build. Local PostgreSQL testing uses `TEST_POSTGRES_URL` and is skipped when that variable is absent. Point it only at a disposable test database: the test drops the application's tables afterward.

Tests with mocked provider calls do not replace a full Sandbox checkout. To check the complete flow, approve a Sandbox payment, return to the app, and confirm that the transaction shows a successful capture.

## Under the hood

| Part | Tools |
|---|---|
| Interface | React, Vite, Lucide React |
| API | Python, FastAPI, Pydantic |
| Database | SQLAlchemy, PostgreSQL with psycopg, SQLite for local use |
| Accounts | PyJWT and Argon2 password hashing |
| Payments | PayPal Sandbox Orders and Vault APIs |
| AI | OpenRouter, using an OpenAI-compatible client |
| Wallet-token encryption | Fernet from `cryptography` |
| Tests | pytest and GitHub Actions |

Backend code lives in `backend/app`, account scripts in `backend/scripts`, and tests in `backend/tests`. The React app and styles are in `frontend/src`.

The API docs at `/docs` show the current request and response formats. Main routes include:

| Area | Routes |
|---|---|
| Accounts | `/api/auth/register`, `/api/auth/login`, `/api/auth/me` |
| Payments | `/api/payments/analyze`, `/api/payments`, `/api/payments/{id}` |
| Spending | `/api/limits/settings`, `/api/limits/summary` |
| Wallet connection | `/api/paypal/connection` |
| Reviews | `/api/reviews/mine`, `/api/reviews/{id}/confirm`, `/api/reviews` |
| Insights and updates | `/api/intelligence/overview`, `/api/intelligence/summary`, `/api/intelligence/notifications` |
| Administration | `/api/admin/overview`, `/api/admin/users`, `/api/admin/payments` |

Payment details require the owning account. Staff and admin routes have separate role checks.

## Current limits

PathGuard Pay is a working project, with more work needed before real-money use:

- Checkout is Sandbox only. Direct payouts and verified PayPal webhooks are not implemented.
- Access tokens are stored in browser localStorage. Session management, rate limiting, and account recovery need further work.
- Budget reservations do not yet use database-level locking for strict concurrent accounting.
- AI output can be wrong. Incident signals are clues to investigate, not confirmed fraud or root causes.
- Notifications are in-app; email and push delivery are not configured.
- Older records without account ownership need reconciliation before any migration to shared production data.

## More from PathGuard

PathGuard Pay focuses on payment instructions and PayPal checkout. Our separate [PathGuard project](https://pathguard.cieltech.org/) focuses on checking crypto destinations before a transfer, with tools for people, developers, and AI agents.

If that's useful to you, [visit PathGuard](https://pathguard.cieltech.org/).

## License

[MIT](LICENSE). Built by [Utee Jacob](https://github.com/Utee) and contributors.
