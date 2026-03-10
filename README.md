# Customer Support Automation Agent

Starter project for a customer support automation workflow:

Customer message -> AI analysis -> KB retrieval -> response draft -> ticket/email update

## Stack

- FastAPI
- LangChain (prompt pipeline in service layer)
- PostgreSQL
- Redis
- Docker + docker-compose
- Hugging Face bootstrap dataset (`bitext/Bitext-customer-support-llm-chatbot-training-dataset`)

## Quick Start

1. Create `.env` from `.env.example`.
2. Build and run services:

```bash
docker compose up --build
```

3. Bootstrap starter data and build KB docs:

```bash
python scripts/bootstrap_data.py
python scripts/build_kb.py
```

4. Test health endpoint:

```bash
curl http://localhost:8000/v1/health
```

5. Process one support message:

```bash
curl -X POST http://localhost:8000/v1/process-message \
  -H "Content-Type: application/json" \
  -d '{
    "ticket_id": "TCK-1001",
    "customer_email": "user@example.com",
    "subject": "Refund question",
    "message": "I want a refund for my delayed order"
  }'
```

6. Run the Streamlit frontend (optional):

```bash
streamlit run frontend/streamlit_app.py
```

7. Run the test suite:

```bash
pytest -q
```

8. Run database migrations (recommended for non-dev setups):

```bash
alembic upgrade head
```

## Data Bootstrap

- `scripts/bootstrap_data.py`: downloads and samples Hugging Face customer support records into JSONL.
- `scripts/build_kb.py`: converts sampled records into local markdown KB files in `data/kb/`.

## Project Layout

- `app/api/routes.py`: API endpoints.
- `app/services/agent.py`: support agent orchestration.
- `app/services/retriever.py`: local KB retrieval.
- `app/adapters/`: email and ticket integration boundaries.
- `scripts/`: data bootstrap and KB build utilities.
- `tests/`: starter tests.
- `frontend/streamlit_app.py`: lightweight UI for single and batch ticket processing.

## Production Notes

- Replace adapter stubs with real Zendesk/Gmail implementations.
- Add auth, RBAC, and audit persistence.
- Add queue-backed async processing for higher ticket volume.

## Engineering Quality

- Test suite: `30 passed`.
- CI pipeline: GitHub Actions workflow at `.github/workflows/ci.yml` runs `pytest -q` on push and PR.
- Runtime startup: FastAPI lifespan startup is used (no deprecated startup event hook).
- Container hardening: non-root user and container health checks are enabled.

## Deployment

### Backend (Render)

1. In Render, click `New` -> `Blueprint`.
2. Select this GitHub repo and keep `render.yaml` enabled.
3. Set required secret env vars in Render dashboard:
  - `OPENAI_API_KEY`
  - `ZENDESK_BASE_URL`, `ZENDESK_EMAIL`, `ZENDESK_API_TOKEN`
  - `GMAIL_SENDER_EMAIL`, `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REFRESH_TOKEN`
4. Deploy and copy backend URL, then verify health:

```bash
curl https://<your-render-backend>/v1/health
```

### Frontend (Streamlit Community Cloud)

1. In Streamlit Cloud, create app from this repo.
2. Set file path to `frontend/streamlit_app.py`.
3. Add app secret in Streamlit settings:

```toml
STREAMLIT_API_BASE_URL = "https://<your-render-backend>"
```

4. Deploy and open the app URL.

## Production Checklist

- Configure real integration credentials in `.env` (`ZENDESK_*`, `GMAIL_*`).
- Set `EMAIL_DELIVERY_MODE=live` only in secured environments.
- Enable API protection in `.env`:
  - `API_AUTH_ENABLED=true`
  - `API_KEY=<strong-random-secret>`
  - `API_KEY_HEADER=X-API-Key` (or your preferred header)
- Enable request throttling in `.env`:
  - `RATE_LIMIT_ENABLED=true`
  - `RATE_LIMIT_REQUESTS=60`
  - `RATE_LIMIT_WINDOW_SECONDS=60`
- Use a managed PostgreSQL/Redis service and update `POSTGRES_DSN` and `REDIS_URL`.
- Add API authentication and request rate limiting before internet exposure.
- Enable structured app logs and central log collection.

## Migrations

- Initialize or upgrade schema: `alembic upgrade head`
- Create new migration after schema changes: `alembic revision -m "describe change"`
- Roll back one migration: `alembic downgrade -1`

## Gmail Refresh Token Setup

If you are using Gmail integration, generate a one-time refresh token from your OAuth client JSON:

```bash
python scripts/generate_gmail_refresh_token.py --client-json client_secret_*.json
```

Then copy the printed values into `.env`:

- `GMAIL_CLIENT_ID`
- `GMAIL_CLIENT_SECRET`
- `GMAIL_REFRESH_TOKEN`
