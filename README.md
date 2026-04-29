# Milk Ledger System

Production-ready repo layout for a zero-cost deployment setup:

- `frontend/` -> Vercel free tier
- `backend/` -> Render free tier
- `Supabase` -> primary database
- `Google Sheets` -> optional secondary backup later
- `GitHub` -> source control + auto deploy trigger

This project keeps the working Flask dashboard and WhatsApp bot in the backend, and adds a lightweight Vercel-hosted frontend launchpad that reads the backend URL from environment configuration at runtime.

## Final Folder Structure

```text
milk-ledger/
│
├── frontend/
│   ├── api/
│   │   └── config.js
│   ├── app.js
│   ├── index.html
│   └── vercel.json
│
├── backend/
│   ├── app/
│   │   ├── models/
│   │   ├── routes/
│   │   ├── services/
│   │   ├── static/
│   │   ├── templates/
│   │   ├── utils/
│   │   ├── extensions.py
│   │   ├── forms.py
│   │   └── __init__.py
│   ├── .env
│   ├── app.py
│   ├── config.py
│   ├── Procfile
│   ├── requirements.txt
│   ├── sample_data.sql
│   └── supabase_schema.sql
│
├── .env.example
├── .gitignore
├── render.yaml
└── README.md
```

## Architecture Diagram

```text
                GitHub
                  │
         ┌────────┴────────┐
         │                 │
         ▼                 ▼
   Vercel Frontend    Render Backend
   (static launchpad) (Flask app + bot)
         │                 │
         └────────┬────────┘
                  ▼
               Supabase
                  │
                  ▼
        Optional Google Sheets backup
```

## What Is Production-Ready Now

### Backend

- Flask app runs on `0.0.0.0` with `PORT` fallback for Render
- `gunicorn app:app` compatible
- `/health` route returns `OK`
- `/health/live` returns structured health JSON
- incoming WhatsApp message logging
- retry support for outbound WhatsApp API calls
- CSRF protection
- secure session handling
- safer logout and redirect handling
- master-key protection on sensitive farmer and entry operations
- service-layer validation for milk entries

### Frontend

- deployable static site for Vercel
- runtime backend URL from env via `frontend/api/config.js`
- no `localhost` dependency
- launchpad links to backend login and health check

## Environment Variables

Use the root [.env.example](D:\My projects\Milk Assistent\.env.example) as the template.

### Frontend (Vercel)

- `API_URL`

Example:

```env
API_URL=https://your-backend.onrender.com
```

### Backend (Render)

- `APP_ENV`
- `SECRET_KEY`
- `PASSWORD_RESET_KEY`
- `APP_BASE_URL`
- `PREFERRED_URL_SCHEME`
- `SESSION_COOKIE_SECURE`
- `SESSION_COOKIE_SAMESITE`
- `SESSION_TIMEOUT_MINUTES`
- `MAX_CONTENT_LENGTH`
- `TRUST_PROXY`
- `TRUSTED_HOSTS`
- `BUSINESS_NAME`
- `SUPABASE_URL`
- `SUPABASE_KEY`
- `SUPABASE_SCHEMA`
- `ACCESS_TOKEN`
- `VERIFY_TOKEN`
- `WHATSAPP_PHONE_NUMBER_ID`
- `WHATSAPP_BUSINESS_ACCOUNT_ID`
- `WHATSAPP_OWNER_PHONE`
- `WHATSAPP_API_BASE`
- `LOG_LEVEL`

## Local Setup

### 1. Create Python environment

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r backend\requirements.txt
```

### 2. Local backend secrets

Copy the root `.env.example` values into:

```text
backend/.env
```

Fill in your real backend values there.

### 3. Run Supabase schema

Run:

- [backend/supabase_schema.sql](D:\My projects\Milk Assistent\backend\supabase_schema.sql)

in the Supabase SQL Editor.

### 4. Run the backend locally

```powershell
.\.venv\Scripts\activate
python backend\app.py
```

### 5. Open the local backend

```text
http://127.0.0.1:10000/login
```

The Vercel frontend is not required for local backend work.

## Backend Deployment on Render

### Option A: Use `render.yaml`

This repo includes:

- [render.yaml](D:\My projects\Milk Assistent\render.yaml)

It defines a free-tier Python web service with:

- build command: `pip install -r backend/requirements.txt`
- start command: `gunicorn --chdir backend app:app`
- health path: `/health`

### Option B: Manual Render setup

In Render:

1. Create a new `Web Service`
2. Connect your GitHub repo
3. Use these values:

```text
Runtime: Python 3
Build Command: pip install -r backend/requirements.txt
Start Command: gunicorn --chdir backend app:app
```

4. Add backend env vars from `.env.example`
5. Set:

```text
APP_ENV=production
SESSION_COOKIE_SECURE=true
TRUST_PROXY=true
```

6. Set `TRUSTED_HOSTS` to your actual backend domain, for example:

```text
your-backend.onrender.com
```

### Render health checks

- `GET /health` -> `OK`
- `GET /health/live` -> JSON health payload

## Frontend Deployment on Vercel

The frontend is a static Vercel site inside:

- [frontend/](D:\My projects\Milk Assistent\frontend)

### Vercel setup

1. Import your GitHub repo into Vercel
2. Set the project root to:

```text
frontend
```

3. Add this env var in Vercel:

```text
API_URL=https://your-backend.onrender.com
```

4. Deploy

The frontend uses:

- [frontend/api/config.js](D:\My projects\Milk Assistent\frontend\api\config.js)

to read `API_URL` at runtime from Vercel environment variables.

## GitHub Setup

### Initialize repo

If not already initialized:

```powershell
git init
git add .
git commit -m "Initial production-ready structure"
```

### `.gitignore`

The repo includes:

- [`.gitignore`](D:\My projects\Milk Assistent\.gitignore)

It ignores:

- `.env`
- `backend/.env`
- `__pycache__`
- `.venv`
- `node_modules`
- `.vercel`

## Auto Deploy Flow

### Vercel

When connected to GitHub, Vercel deploys pushes automatically. This is documented by Vercel’s Git deployment docs: [Deploying GitHub Projects with Vercel](https://vercel.com/docs/deployments/git/vercel-for-github).

### Render

Render web services deploy automatically on pushes to the connected branch. This is documented in Render’s Flask deployment guide: [Deploy a Flask App on Render](https://render.com/docs/deploy-flask).

### Daily update workflow

```text
Local changes
   ↓
git add .
git commit -m "your update"
git push origin main
   ↓
Render auto deploys backend
Vercel auto deploys frontend
```

## Exact Commands To Run

### Local install

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r backend\requirements.txt
```

### Local backend run

```powershell
python backend\app.py
```

### Git init and first commit

```powershell
git init
git add .
git commit -m "Initial production-ready structure"
```

### Push to GitHub

```powershell
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git branch -M main
git push -u origin main
```

## Notes For Long-Term Maintainability

- keep secrets only in Render and Vercel env settings
- do not commit `backend/.env`
- keep Supabase service role key server-side only
- use the Vercel frontend as the public launchpad
- use the Render backend for login, dashboard, webhooks, and PDF generation
- when changing schema, update `backend/supabase_schema.sql` first

## Recommended Next Upgrade

If you want a more advanced production phase after this, the next clean upgrades are:

1. Google Sheets backup sync worker
2. dedicated API endpoints for a richer Vercel frontend
3. webhook signature verification if Meta introduces or requires stricter validation in your flow
4. CI checks with GitHub Actions
