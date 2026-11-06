# TokoBantu

Customer service assistant for a Shopify development store. The API serves a customer chat page and a small staff ticket panel. Product, order, policy, and escalation logic lives in `app/tools/`; the web layer is in `app/main.py`.

## Run locally

Use Python 3.13 and the existing virtual environment. Configure these environment variables in your local environment or private `.env` file; never commit secrets:

- `SHOPIFY_STORE`, `SHOPIFY_CLIENT_ID`, `SHOPIFY_CLIENT_SECRET` for Shopify access.
- `GEMINI_API_KEY` for live agent replies. `GEMINI_MODEL` is optional.
- `STAFF_TOKEN` for staff access. Staff routes return `503` when this value is empty.
- `TOKOBANTU_DB` is optional for local development; the default SQLite path is `data/tokobantu.db`.
- `DATABASE_URL` or `TOKOBANTU_DATABASE_URL` enables Postgres for tickets, chat sessions, and shared rate limits. Vercel requires this persistent storage; SQLite is local-only there.

In PowerShell, activate the environment and start the web server:

```powershell
.venv\Scripts\Activate.ps1
python -m app.main
```

The server listens on `http://127.0.0.1:8001`.

- Customer chat: `http://127.0.0.1:8001/`
- Staff ticket panel: `http://127.0.0.1:8001/staff.html`
- API schema: `http://127.0.0.1:8001/docs`
- Health: `http://127.0.0.1:8001/health`

The staff panel asks for the bearer token at sign-in and keeps it in page memory only. It is cleared when staff signs out or leaves the page.

## Vercel staging

The project includes Vercel's FastAPI entrypoint and function configuration. Deploy from the repository root; do not upload `.env`, `data/`, or `logs/`. Vercel runs FastAPI as a Python Function and serves the static frontend from the same deployment.

1. Import the repository into Vercel and create a **Preview** deployment first.
2. Add a Postgres integration from Vercel Marketplace (Neon is a suitable free-tier option for a small personal demo). Connect it to the project so Vercel provides `DATABASE_URL`.
3. Set `TOKOBANTU_STORAGE_MODE=postgres` to prevent any fallback to function-local storage.
4. Set `SHOPIFY_STORE`, `SHOPIFY_CLIENT_ID`, `SHOPIFY_CLIENT_SECRET`, `GEMINI_API_KEY`, and a newly generated `STAFF_TOKEN` in the Vercel Preview environment. Set `GEMINI_MODEL` if you want to override the default.
5. Set `RATE_LIMIT_SECRET` to a separate random secret. If omitted, the application derives its HMAC key from `STAFF_TOKEN`, then `GEMINI_API_KEY`.
6. Redeploy Preview and check `/health`, `/`, `/staff.html`, chat, and ticket creation/closure before promoting anything.

Use only the Shopify development store and synthetic customer records in a public demo. Never give reviewers Shopify credentials. Keep the database integration scoped to Preview until the staging deployment is verified. Vercel's Hobby plan is free for personal, non-commercial use and has usage limits; review the current plan limits before deployment.

In hosted mode, the API stores chat history with a 30-minute expiry and stores rate-limit events using keyed hashes of session/IP identifiers. Raw IPs are not stored in the rate-limit table. Ticket data is retained in Postgres until staff closes or otherwise manages the record.

## Chat and session behavior

The browser creates a UUID for each page session and sends it with every chat message. In local development, the API keeps up to 500 histories in memory, each capped at the most recent 20 messages and expired after 30 minutes of inactivity. Local rate limits are in memory and reset when the server restarts. In Vercel mode, histories and shared per-session/per-IP rate-limit events use Postgres so requests can move between serverless instances; histories still expire after 30 minutes, retain at most 20 messages, and are capped at 500 active sessions.

## Offline tests

Run the deterministic tests without loading `.env` or contacting Shopify/Gemini:

```powershell
$env:PYTHON_DOTENV_DISABLED = "true"
.venv\Scripts\python.exe scripts\test_api.py
.venv\Scripts\python.exe scripts\test_agent.py
.venv\Scripts\python.exe scripts\test_escalation.py
.venv\Scripts\python.exe scripts\test_policy.py
.venv\Scripts\python.exe scripts\test_scenarios.py
```

`test_api.py` uses FastAPI `TestClient` and a fake agent. `test_scenarios.py` mocks Shopify GraphQL responses for stock and order verification cases. The scripts `test_orders.py`, `test_tools.py`, `test_shopify.py`, and `test_gemini.py` are integration checks that contact the configured development store or Gemini service; run those separately when credentials and network access are available.

## Data and privacy notes

- Shopify operations are read-only.
- Order status is returned only after order number and customer email verification.
- Staff ticket routes require `Authorization: Bearer <STAFF_TOKEN>`.
- Tool-call logs record parameter names and timing, not parameter values or message content.
- Ticket contact details are stored in the local SQLite database for staff follow-up.

