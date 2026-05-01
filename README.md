# Milk Ledger System

Production deployment layout for the milk ledger dashboard and WhatsApp webhook backend.

## Architecture

```text
GitHub
  |
  +-- Vercel -> frontend/
  |
  +-- Render -> backend/
               |
               +-- Supabase PostgREST
               +-- Supabase Postgres (migrations / validation / self-heal)
```

## Folder Structure

```text
milk-ledger/
├── backend/
│   ├── app/
│   ├── app.py
│   ├── config.py
│   ├── manage_db.py
│   ├── Procfile
│   ├── requirements.txt
│   └── tests/
├── frontend/
├── supabase/
│   └── migrations/
├── .env.example
├── render.yaml
└── README.md
```

## Database Source Of Truth

All schema changes live in [D:\My projects\Milk Assistent\supabase\migrations](D:\My projects\Milk Assistent\supabase\migrations).

Current migration file:
- [D:\My projects\Milk Assistent\supabase\migrations\202605010001_production_baseline.sql](D:\My projects\Milk Assistent\supabase\migrations\202605010001_production_baseline.sql)

The `session_closures` table is managed with:
- `id uuid primary key`
- `session_name text not null`
- `target_date date not null`
- `is_closed boolean not null default false`
- `created_at timestamptz not null default now()`
- unique constraint on `(session_name, target_date)`

## Environment Variables

Copy [D:\My projects\Milk Assistent\.env.example](D:\My projects\Milk Assistent\.env.example) and set real values.

Required backend values:
- `SUPABASE_URL`
- `SUPABASE_KEY`
- `SUPABASE_DB_URL`
- `SECRET_KEY`
- `PASSWORD_RESET_KEY`

Required `SUPABASE_DB_URL` format:

```text
postgresql://postgres:YOUR_PASSWORD@db.YOUR_PROJECT_REF.supabase.co:5432/postgres?sslmode=require
```

Notes:
- use `postgresql://`, not `http://` or your Supabase project URL
- use the direct Postgres connection string, not the REST URL
- keep `sslmode=require`
- the app normalizes `postgres://` to `postgresql://`, but Render should still be configured with the full correct format

Required frontend value:
- `API_URL`

## Local Setup

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r backend\requirements.txt
```

Create `backend/.env` from `.env.example`.

Run migrations with the Supabase CLI:

```powershell
supabase migration new add_your_change
supabase db push --db-url "$env:SUPABASE_DB_URL"
```

Validate schema locally:

```powershell
.\.venv\Scripts\activate
python backend\manage_db.py
```

Start the backend:

```powershell
python backend\app.py
```

Run tests:

```powershell
pytest backend\tests -q
```

## Runtime Safety

Startup now does all of this before serving traffic:
- checks required tables
- attempts automatic migration repair if tables are missing
- reloads the PostgREST schema cache with `NOTIFY pgrst, 'reload schema';`
- continues in degraded mode if direct DB admin access or network validation is temporarily unavailable

All Supabase table access goes through a safe wrapper in [D:\My projects\Milk Assistent\backend\app\services\supabase_service.py](D:\My projects\Milk Assistent\backend\app\services\supabase_service.py). If a missing-table error is detected, the backend:

1. runs migrations
2. reloads the PostgREST schema
3. retries the query once

## Render Deployment

Render config lives in [D:\My projects\Milk Assistent\render.yaml](D:\My projects\Milk Assistent\render.yaml).

Build command:

```text
pip install -r backend/requirements.txt
```

Start command:

```text
python backend/manage_db.py && gunicorn --chdir backend app:app
```

This repo uses the start command for migration validation because your Render setup is on the free tier. Render's separate `preDeployCommand` is not available on free web services, so the application performs migration/app-start sequencing inside the start command instead.

Required Render env vars:
- `APP_ENV=production`
- `SESSION_COOKIE_SECURE=true`
- `TRUST_PROXY=true`
- `SUPABASE_URL`
- `SUPABASE_KEY`
- `SUPABASE_DB_URL`
- `TRUSTED_HOSTS`

Render check for `SUPABASE_DB_URL`:
- host should look like `db.<project-ref>.supabase.co`
- database should be `postgres`
- query string should include `sslmode=require`

Deploy flow:
1. Render installs dependencies.
2. Render runs `python backend/manage_db.py`.
3. Migrations are applied from `supabase/migrations`.
4. If the Supabase CLI is unavailable on Render, the app falls back to direct SQL migration execution using `SUPABASE_DB_URL`.
5. Schema is validated when possible.
6. If validation is temporarily unavailable, the service still starts in degraded mode and logs the exact reason.

Render auto-deploy reference: [Render deploys](https://render.com/docs/deploys/)

## Vercel Deployment

Set the Vercel project root to `frontend/`.

Required Vercel env var:

```text
API_URL=https://your-backend.onrender.com
```

Vercel auto-deploy reference: [Deploying GitHub Projects with Vercel](https://vercel.com/docs/deployments/git/vercel-for-github)

## Update Workflow

1. Create or edit SQL in `supabase/migrations/`
2. Push migrations with the Supabase CLI:

```powershell
supabase db push --db-url "$env:SUPABASE_DB_URL"
```

3. Run tests:

```powershell
pytest backend\tests -q
```

4. Commit and push:

```powershell
git add .
git commit -m "Your change"
git push origin main
```

5. Render and Vercel auto-deploy from GitHub

Supabase migration docs: [Database Migrations](https://supabase.com/docs/guides/deployment/database-migrations)  
Supabase CLI push docs: [supabase db push](https://supabase.com/docs/reference/cli/supabase-inspect-db-role-configs)  
PostgREST schema refresh docs: [Reload/refresh postgrest schema](https://supabase.com/docs/guides/troubleshooting/refresh-postgrest-schema)
