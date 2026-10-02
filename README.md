# Milk Ledger — Dairy Collection and Payments Platform

A production-oriented Flask application for managing a small dairy milk collection workflow: farmer records, daily milk entries, payment tracking, store-credit deductions, reports, PDF generation, and WhatsApp webhook support.

**Live demo:** [https://milk-ledger-pink.vercel.app](https://milk-ledger-pink.vercel.app)

The demo page is a Vercel-hosted frontend that reads the backend URL at runtime and links to the live Render backend health check and dashboard login.

## Why this project exists

Small milk collection centers need a simple operational ledger for daily milk quantity, farmer balances, payments, and store purchases. This project turns that workflow into a web application with deployment automation and runtime safety checks.

## What the application supports

- Admin login and protected dashboard.
- Farmer onboarding and profile management.
- Morning/evening milk entry tracking.
- Rate, quantity, amount, and payment calculations.
- Payment records and monthly settlement support.
- Store transaction tracking for farmer credit/deductions.
- Reports and PDF output.
- WhatsApp webhook endpoint for message-driven workflows.
- Supabase-backed persistence with SQL migrations.
- Health endpoints for platform monitoring.

## Architecture

```text
User browser
  |
  v
Vercel frontend
  |
  | runtime API_URL
  v
Render Flask backend
  |
  +-- Supabase PostgREST API
  +-- Supabase Postgres direct connection for migrations/validation
  +-- Meta WhatsApp Cloud API webhook integration
```

## DevOps and platform evidence

| Area | Evidence in this repo |
|---|---|
| Cloud deployment | `render.yaml` for Render backend and `frontend/vercel.json` for Vercel frontend. |
| Runtime config | `.env.example`, Render/Vercel env vars, trusted host checks, secure cookie settings. |
| Database delivery | Supabase SQL migration under `supabase/migrations/` and startup migration validation. |
| Health checks | `/health` for platform checks and `/health/live` for JSON runtime status. |
| CI/CD | `.github/workflows/backend-ci.yml` runs backend tests and Docker build validation. |
| Containerization | `backend/Dockerfile` plus `.dockerignore`. |
| Security hygiene | CSRF protection, secure headers, host allow-listing, secrets kept in platform env vars. |
| Operations | `docs/runbook.md` documents health checks, deployment triage, webhook verification, and rollback approach. |
| Test coverage | `backend/tests/` covers config validation, degraded startup, migrations, payments, session behavior, request safety, and webhook verification. |

## Repository structure

```text
.
├── .github/workflows/backend-ci.yml
├── backend/
│   ├── app/
│   │   ├── routes/
│   │   ├── services/
│   │   ├── models/
│   │   ├── static/
│   │   └── templates/
│   ├── Dockerfile
│   ├── config.py
│   ├── manage_db.py
│   ├── requirements.txt
│   └── tests/
├── docs/runbook.md
├── frontend/
│   ├── api/config.js
│   ├── app.js
│   ├── index.html
│   └── vercel.json
├── supabase/migrations/
├── render.yaml
├── app.py
├── wsgi.py
└── README.md
```

## Local backend setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cp .env.example backend/.env
python backend/manage_db.py
python app.py
```

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r backend\requirements.txt
Copy-Item .env.example backend\.env
python backend\manage_db.py
python app.py
```

## Run tests

```bash
cd backend
pytest tests -q
```

## Build the backend container

```bash
docker build -f backend/Dockerfile -t milk-ledger-backend:local .
docker run --env-file backend/.env -p 5000:5000 milk-ledger-backend:local
```

## Required environment variables

Backend:

```text
APP_ENV=production
SECRET_KEY=replace-with-a-long-random-secret
PASSWORD_RESET_KEY=replace-with-another-long-random-secret
APP_BASE_URL=https://milk-ledger.onrender.com
PREFERRED_URL_SCHEME=https
SESSION_COOKIE_SECURE=true
TRUST_PROXY=true
TRUSTED_HOSTS=milk-ledger.onrender.com,milk-ledger-pink.vercel.app
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-supabase-service-role-key
SUPABASE_DB_URL=postgresql://postgres:password@db.your-project.supabase.co:5432/postgres?sslmode=require
SUPABASE_SCHEMA=public
```

Frontend:

```text
API_URL=https://milk-ledger.onrender.com
```

WhatsApp integration, when enabled:

```text
WHATSAPP_VERIFY_TOKEN=your-meta-verify-token
WHATSAPP_ACCESS_TOKEN=your-meta-access-token
WHATSAPP_PHONE_NUMBER_ID=your-phone-number-id
WHATSAPP_BUSINESS_ACCOUNT_ID=your-business-account-id
WHATSAPP_OWNER_PHONE=919999999999
WHATSAPP_API_BASE=https://graph.facebook.com/v22.0
```

## Deployment flow

1. Push backend changes to `main`.
2. GitHub Actions runs Python tests and Docker build validation.
3. Render auto-deploys the backend using `render.yaml`.
4. Backend startup runs `python backend/manage_db.py` before `gunicorn wsgi:app`.
5. Supabase migrations and schema validation run during startup when DB admin access is configured.
6. Vercel serves the frontend and injects `API_URL` through `frontend/api/config.js`.
7. Verify with `/health` and `/health/live`.

## Operations

See [docs/runbook.md](docs/runbook.md) for:

- Health-check commands.
- Render backend troubleshooting.
- Vercel frontend runtime config checks.
- Supabase migration flow.
- WhatsApp webhook verification.
- Rollback approach.
- Security hygiene checklist.

## Resume-ready summary

Built and deployed a Flask/Supabase dairy ledger platform for farmer milk collection, payments, store credit, PDF reports, and WhatsApp webhook workflows. Implemented Render/Vercel deployment configuration, Supabase migrations, runtime health checks, secure configuration boundaries, GitHub Actions CI, backend Docker build validation, and an operations runbook.

Suggested resume link:

```text
Milk Ledger demo: https://milk-ledger-pink.vercel.app
```

## Notes for reviewers

This repository is currently private, so use the live demo link in a resume unless repository access is intentionally granted. The project should not expose real farmer data, Supabase service-role keys, WhatsApp tokens, or production database credentials in public screenshots or commits.
