# PathGuard Pay

**A pre-payment safety layer that checks payment instructions before they reach PayPal.**

PathGuard Pay is a hackathon MVP exploring how payment products can make sending money safer. It accepts a payment instruction in natural language, turns it into a structured intent, evaluates it against deterministic risk rules and the user's spending limits, and then decides whether the payment can proceed, needs human review, or must be blocked.

The project combines payment-risk analysis, account-level controls, recipient history, human review, operational intelligence, and a PayPal Sandbox checkout flow in one application.

> **Demo and safety notice:** This project is configured for the PayPal Sandbox. It is a prototype, not a production payment service, and it does not move real money.

## The problem

Payment interfaces make it easy to submit a payment, but they may not give a user or an operations team enough context to judge whether the payment is unusual. A new recipient, an unexpectedly large amount, a changed payment purpose, repeated attempts, or a user's spending-limit breach can all be reasons to pause before money is sent.

PathGuard Pay explores a simple principle: **check first, pay second**. The payment rail should not be the first place a questionable instruction is examined.

## How PathGuard Pay works

```text
User enters a payment instruction
            |
            v
Extract and validate payment intent
            |
            v
Check recipient history, risk rules and spending limits
            |
            v
     ALLOW / REVIEW / BLOCK
        /       |       \
       v        v        v
   Continue   Human     Stop
   checkout   review
       |
       v
PayPal Sandbox approval / saved-wallet flow
       |
       v
Server verifies and captures eligible order
       |
       v
Payment status, history and audit events
```

1. **Describe the payment.** A signed-in user enters an instruction such as “Pay John $200 for the website.”
2. **Structure the intent.** If configured, OpenRouter helps extract payment details from natural language. Otherwise, a conservative local parser is used.
3. **Evaluate the payment.** PathGuard applies deterministic rules, recipient-history signals, and the user's active spending limits.
4. **Apply the decision.** `ALLOW` can continue to checkout, `REVIEW` must be approved by an authorized reviewer, and `BLOCK` cannot proceed.
5. **Complete checkout in Sandbox.** Eligible payments use PayPal Sandbox. The backend verifies the return and performs server-side capture.
6. **Record what happened.** Payment history and audit events support user visibility, review, and operational monitoring.

AI is an assistive component, not the final payment authority. An AI-generated intent or summary cannot override the deterministic risk engine, human-review requirement, or spending limits.

## Features

### 1. Payment risk analysis

- Natural-language payment instructions.
- Structured intent extraction using optional OpenRouter integration, with a local parser fallback.
- Deterministic risk decisions: **ALLOW**, **REVIEW**, or **BLOCK**.
- Checks for unusually large payments and recipient-specific amount anomalies.
- Account-scoped recipient profiles built from completed payment history.
- Signals for new recipients, changed payment purposes, and rapid repeat payments.
- Payment detail and audit timelines for investigating a decision.

### 2. User accounts and spending controls

- Customer registration and sign-in using bearer access tokens.
- Separate customer payment history and spending policies.
- Configurable daily, weekly, monthly, and optional per-transaction limits.
- A timezone setting for spending-period boundaries.
- Server-side enforcement throughout the payment lifecycle, including checks before checkout/capture.
- Budget reservations for eligible in-flight payments to reduce the chance of concurrent attempts exceeding a limit.
- USD-denominated spending policies; unsupported non-USD payments are blocked rather than silently converted.

Default limits are **USD 1,000 per day**, **USD 10,000 per week**, and **USD 10,000 per month**, using `Africa/Lagos` period boundaries. Users can adjust supported limits in the application.

### 3. PayPal Sandbox checkout and saved wallet

- Create PayPal Sandbox orders for eligible payment requests.
- Standard PayPal-hosted buyer approval flow.
- Server-side order verification and capture.
- Idempotent capture handling.
- Optional PayPal Vault connection flow for users who want to save a Sandbox wallet.
- Encrypted storage for saved-wallet tokens; tokens are not returned by the API.
- PathGuard checks still run before a saved-wallet payment is attempted.

Saved-wallet functionality requires Vault to be enabled in the PayPal Sandbox REST app and the encryption key to be configured. PayPal may still require the payer to take action.

### 4. Human review workflow

- A queue for payments with a `REVIEW` decision.
- Reviewer approval or rejection with notes and review events.
- A payment cannot proceed from `REVIEW` until an authorized reviewer approves it.
- Reviewer identity comes from the authenticated account rather than trusting an identity submitted by the client.

### 5. Operational intelligence and notifications

- Dashboard metrics for payment outcomes, completed spend, blocked attempts, operational errors, and success rate.
- Heuristic detection for recurring PayPal errors, stale checkouts, spending-limit block spikes, and unusual risk-block volumes.
- On-demand operational summaries with an OpenRouter option and deterministic fallback.
- In-app notifications based on audit events, including blocks, review requests, PayPal failures, cancellations, stale checkouts, and completed payments.
- Customer views are account-scoped; reviewer/admin views can include organization-wide operational signals.

Incident detections are investigative signals, not confirmed root causes. Email and push notifications are not configured in this MVP.

### 6. Admin dashboard

Administrators have a dedicated area for platform-wide oversight, including:

- User and account overview metrics.
- Searchable user management.
- Role and account-status controls.
- Platform-wide payment monitoring.
- Payment and operational activity visibility.

Admin endpoints are protected by role checks. The first administrator or staff account should be provisioned through the backend CLI and the deployment environment should be secured.

## Technology stack

| Area | Technology | Purpose |
|---|---|---|
| Frontend | React 19 | Interactive user, reviewer, and admin dashboards |
| Frontend tooling | Vite 6, JavaScript/TypeScript tooling | Local development and production build |
| UI icons | Lucide React | Interface icons |
| Backend | Python, FastAPI | REST API and application workflows |
| API validation | Pydantic / pydantic-settings | Request validation and configuration |
| Database layer | SQLAlchemy | Persistence and database access |
| Local database | SQLite | Lightweight local MVP storage |
| Authentication | PyJWT, pwdlib with Argon2 | Signed access tokens and password hashing |
| Payment provider | PayPal REST API Sandbox | Sandbox orders, approval, capture, and Vault connection |
| AI integration | OpenRouter through the OpenAI-compatible client | Optional intent extraction and operational summaries |
| Wallet-token encryption | cryptography / Fernet | Encrypt saved PayPal payment tokens at rest |
| Testing | pytest | Backend and risk workflow tests |
| API exploration | FastAPI OpenAPI / Swagger UI | Interactive API documentation |

OpenRouter is optional. Without an API key, the application uses its local intent parser and deterministic operational-summary fallback. The core risk decision and spending-limit enforcement do not depend on an LLM response.

## Architecture at a glance

- **React frontend** sends authenticated requests to the API.
- **FastAPI backend** validates requests and enforces authorization.
- **Risk and limits logic** evaluates payment intent, recipient context, and spending policy before checkout.
- **SQLAlchemy persistence** stores users, payment requests, risk assessments, review records, wallet connection data, and audit events.
- **PayPal Sandbox adapter** handles order creation, payer approval, verification, and capture.
- **Intelligence endpoints** summarize aggregate operational metrics and derive heuristic incident signals from stored events.

The backend is the enforcement boundary: a frontend decision or a generated AI summary is not sufficient to authorize a payment.

## Repository layout

```text
.
├── backend/
│   ├── app/
│   │   ├── api/          # Authentication, payments, limits, reviews, admin and intelligence APIs
│   │   ├── core/         # Configuration and security utilities
│   │   └── ...           # Models, database setup and service logic
│   ├── scripts/          # Staff account provisioning utilities
│   ├── tests/            # Backend and risk workflow tests
│   ├── requirements.txt
│   └── .env.example
└── frontend/
    ├── src/              # React application and styles
    ├── package.json
    └── vite.config.*
```

## Getting started

### Prerequisites

- Python 3.11 or newer
- Node.js 18 or newer and npm
- Git
- PayPal Developer Sandbox credentials for checkout testing
- An OpenRouter API key only if you want the optional AI features

### 1. Clone the repository

```bash
git clone https://github.com/Utee/pathguard-pay-mvp.git
cd pathguard-pay-mvp
```

### 2. Configure and run the backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

On Windows PowerShell, activate the environment with:

```powershell
.venv\Scripts\Activate.ps1
```

Generate a strong JWT signing secret:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Copy the generated value into `JWT_SECRET_KEY` in `backend/.env`. Do not leave the signing key blank or commit your real `.env` file.

For optional AI functionality, set `OPENROUTER_API_KEY`. The model and OpenRouter-compatible base URL can be configured using `OPENROUTER_MODEL` and `OPENROUTER_BASE_URL`.

For saved PayPal wallet support, generate a Fernet key:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Set the result as `PAYPAL_VAULT_ENCRYPTION_KEY` in `backend/.env`. Keep it private and stable: changing or losing the key can make previously stored wallet tokens unreadable. Configure your PayPal Sandbox Client ID and Secret, and set the PayPal connection callback URLs if testing the Vault flow on a hosted deployment. Enable both **Accept payments** and **Vault** in the Sandbox REST app's advanced settings when using saved wallets.

Start the API from the `backend/` directory:

```bash
uvicorn app.main:app --reload
```

The API is available at `http://127.0.0.1:8000`.

### 3. Create a customer or staff account

You can register a customer through the application. New registrations receive the `customer` role.

To provision a reviewer or administrator, run the staff-account script from the backend directory:

```bash
python scripts/create_user.py staff@example.com --name "PathGuard Reviewer" --role reviewer
```

For an administrator, use `--role admin` instead. The script prompts for the password. Do not expose staff provisioning access or grant administrator privileges to untrusted users.

### 4. Run the frontend

Open a second terminal from the repository root:

```bash
cd frontend
npm install
npm run dev
```

Vite prints the local frontend URL when it starts. By default, the frontend uses the local API at `http://127.0.0.1:8000`. To use another backend, create `frontend/.env`:

```env
VITE_API_URL=http://127.0.0.1:8000
```

Ensure the backend's CORS allowlist includes the frontend origin you use.

### 5. Open the API docs

- Swagger UI: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- Health check: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)

## Testing

For hosted setup, see [Render deployment](docs/render-deployment.md). The root
`render.yaml` defines the frontend, paid API, and paid PostgreSQL database.

Run the backend tests from the backend directory:

```bash
cd backend
pytest
```

The deterministic risk tests do not require PayPal or OpenRouter credentials. Checkout and optional AI flows need the corresponding Sandbox credentials or API key to be exercised end to end.

Build the frontend for production:

```bash
cd frontend
npm install
npm run build
```

## API overview

The backend exposes REST endpoints grouped around these workflows. The interactive Swagger documentation at `/docs` is the source of truth for request and response schemas.

| Workflow | Representative endpoints | Purpose |
|---|---|---|
| Authentication | `/api/auth` | Register and authenticate users |
| Payment analysis and history | `/api/payments` | Analyze instructions and retrieve payment records |
| Spending limits | `/api/limits/settings`, `/api/limits/summary` | Configure caps and inspect current usage |
| PayPal connection | `/api/paypal/connection` | Check, set up, or disconnect a saved Sandbox wallet |
| Human review | `/api/reviews` | Inspect and resolve payments requiring review |
| Operational intelligence | `/api/intelligence/overview`, `/api/intelligence/incidents`, `/api/intelligence/summary` | Metrics, heuristic incident signals, and summaries |
| Notifications | `/api/intelligence/notifications` | Read recent in-app operational events |
| Administration | `/api/admin/overview`, `/api/admin/users`, `/api/admin/payments` | Admin metrics, user management, and platform payment monitoring |
| Health | `/health` | Service health check |

Private payment and account data require authentication. Access to staff and admin operations is role-protected.

## Security and known limitations

This is a hackathon MVP. It demonstrates a payment safety workflow, but it is **not production-hardened**.

- PayPal is configured for Sandbox use; no real-money payment flow is intended.
- Keep PayPal credentials, JWT signing secrets, OpenRouter keys, and encryption keys out of source control.
- Browser access tokens are stored in localStorage in this MVP. A production implementation should review session storage, token revocation, and related browser security risks.
- Authentication hardening such as rate limiting, account recovery, and broader abuse controls remains necessary before production.
- Spending limits are checked across the payment lifecycle, but the current MVP does not use database-level locking for strict concurrent reservation accounting. Production use needs transactional locking and load testing.
- Spending limits are denominated in USD. Non-USD payments are blocked until currency-specific policy or reliable conversion support exists.
- Incident detection is heuristic and should support investigation, not be treated as proof of fraud or a confirmed root cause.
- AI-generated extraction and summaries are fallible; deterministic rules and explicit review controls remain authoritative.
- Email and push notification delivery are not configured.
- Historical payment records created before account ownership was introduced need explicit reconciliation before any multi-user production migration.
- Production deployment, PayPal webhook verification, rate limiting, structured monitoring, and other hardening tasks require further work.

## Roadmap

Potential next steps include:

- Strengthen authentication, rate limiting, and session management.
- Add verified PayPal webhook handling and improve reconciliation for asynchronous payment events.
- Add database locking and concurrency tests for spending-limit reservations.
- Expand instruction-versus-intent mismatch detection and risk explanations.
- Add reviewed policy configuration and richer operational audit tooling.
- Validate a PostgreSQL-backed deployment and production monitoring.
- Explore additional payment rails and reusable PathGuard risk APIs.

## Hackathon project summary

PathGuard Pay demonstrates how a safety layer can sit **between a user's payment instruction and a payment provider**. Rather than treating every instruction as a checkout command, it combines structured intent, deterministic risk checks, recipient context, spending limits, human review, and auditability before an eligible payment reaches PayPal Sandbox.

The goal is not to replace the payment provider. It is to add an explainable checkpoint before the payment is attempted.

---

Built as a hackathon MVP by [Utee Jacob](https://github.com/Utee) and contributors.

