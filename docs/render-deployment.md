# Render deployment

The root `render.yaml` provisions a paid FastAPI web service, a free React static
site, and a paid PostgreSQL database with 1 GB storage. The API and database use
Oregon and the database accepts internal connections only. Applying the Blueprint
incurs recurring charges; review Render's displayed estimate before applying it.
Existing services in the workspace are not part of this Blueprint.

## Before deploying

1. Merge the deployment changes into the branch Render will deploy.
2. Connect Render to this GitHub repository, then create a Blueprint from it.
3. Review the resource plans: API `0.5c-512mb`, database `0.1c-256mb`, static frontend.
4. Supply the PayPal **Sandbox** client ID and secret and an OpenRouter API key
   through Render's secret fields. Never put them in GitHub or the frontend.
5. The Blueprint automatically sets `CORS_ALLOWED_ORIGINS` and `PAYPAL_FRONTEND_URL`
   from the frontend's assigned Render URL. No temporary frontend URL is needed.

Render generates the JWT signing key and a 256-bit URL-safe base64 key suitable
for Fernet. Keep both stable. Changing the wallet encryption key prevents old
saved-wallet tokens from being decrypted. Vault must also be enabled in the
PayPal Sandbox REST app before testing wallet connections.

`DATABASE_URL` comes from the database's internal connection string. The backend
normalizes both `postgres://` and `postgresql://` URLs to the installed psycopg 3
driver, and uses a small connection pool with connection health checks.

`PUBLIC_API_URL` comes from the API's Render URL. It derives these PayPal callbacks:

- `/api/payments/paypal/return`
- `/api/payments/paypal/cancel`
- `/api/paypal/connection/return`
- `/api/paypal/connection/cancel`

Explicit `PAYPAL_*_RETURN_URL` or `PAYPAL_*_CANCEL_URL` values override derivation.
Do not copy localhost callback values from `.env.example` into the hosted service.
The frontend's `VITE_API_URL` references the API's public URL at build time.
Changing this value requires rebuilding the frontend.

The API creates its schema and applies existing additive migrations on startup.
This is a new, empty PostgreSQL database: local SQLite users, payment history, and
wallet tokens are **not** migrated automatically. Register a new demo account.
Use the backend staff-provisioning script from an authorized Render shell for an
admin account; do not add automatic public admin registration or a seeded password.

## Verification

1. Confirm the API's `/health` endpoint returns `status: ok` and the frontend loads.
2. Register and sign in, save spending limits, then refresh to confirm persistence.
3. With OpenRouter configured, analyze a natural-language payment instruction.
4. Exercise ALLOW, REVIEW with password confirmation, and BLOCK paths.
5. Complete PayPal Sandbox approval and verify capture, completed status, and audit
   details after returning to the frontend. Test cancellation as well.
6. Redeploy the API and confirm the account and history remain available.
7. Test saved-wallet connection separately if Vault is enabled.

Tests: run `PYTHONPATH=. pytest -q` from `backend`, and `npm ci && npm run build`
from `frontend`. CI includes a disposable PostgreSQL 16 service for schema creation,
repeat initialization, and JSON audit persistence. Locally that test is skipped
unless `TEST_POSTGRES_URL` is set. **Only point it at a disposable test database:**
it drops the application's tables when finished.

Validate the Blueprint with `render blueprints validate render.yaml` when Render
CLI v2.7+ is installed. JSON Schema validation alone cannot confirm account access,
secret configuration, or deployment success.

## Billing

Keep the workspace on Hobby. The paid database avoids the Free database's 30-day
expiry, and the paid API avoids idle spin-down. Workspace credit offsets invoices
but does not cap spending or automatically change compute plans. Monitor credit
balance and usage, and review costs before credit runs out. No other paid services,
replicas, high availability, or automatic preview environments are configured.
