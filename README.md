# PathGuard Pay — Local MVP

AI payment safety layer for PayPal Sandbox.

## What this first milestone does

1. Accepts a natural-language payment instruction.
2. Extracts a structured payment intent using OpenAI when configured.
3. Falls back to a small local parser when `OPENAI_API_KEY` is absent.
4. Runs the intent through deterministic PathGuard risk rules.
5. Returns `ALLOW`, `REVIEW`, or `BLOCK`.
6. Includes PayPal Sandbox service code for OAuth, Create Order, Get Order, and Capture.
7. Starts with SQLite so the project runs locally with no database server.

> No real money is moved by this project. PayPal integration is intended for the Sandbox.

## Requirements

- Python 3.11+
- Optional: PayPal Developer Sandbox app credentials
- Optional: OpenAI API key

## 1. Create the environment

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
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

## 2. Run the API

```bash
uvicorn app.main:app --reload
```

Open:

- API docs: http://127.0.0.1:8000/docs
- Health: http://127.0.0.1:8000/health

## 3. Test the risk engine without any credentials

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

## 4. PayPal Sandbox

Create a Sandbox REST app in the PayPal Developer Dashboard and put the Client ID and Secret in `.env`.

The backend uses PayPal's Sandbox REST base URL:

`https://api-m.sandbox.paypal.com`

The normal Checkout flow is:

Create Order -> buyer approval -> Capture Order.

The project intentionally keeps PayPal credentials on the server.

## Current API

### POST `/api/payments/analyze`

Request:

```json
{
  "instruction": "Pay John $200 for the website"
}
```

### GET `/api/payments`

Returns locally stored payment requests.

### GET `/api/payments/{payment_id}`

Returns a payment request and risk assessment.

### POST `/api/payments/{payment_id}/paypal/create`

Creates a PayPal Sandbox order only when the payment is allowed to proceed.

### POST `/api/payments/{payment_id}/paypal/capture`

Captures an approved PayPal order.

## Next milestone

- React dashboard
- PayPal JavaScript SDK checkout button
- Persistent recipient history
- Human review flow
- PayPal webhook verification
- Better AI intent extraction
- Audit timeline
