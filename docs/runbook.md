# Milk Ledger Operations Runbook

## Service URLs

| Component | URL |
|---|---|
| Public demo frontend | `https://milk-ledger-pink.vercel.app` |
| Backend default URL | `https://milk-ledger.onrender.com` |
| Basic health check | `https://milk-ledger.onrender.com/health` |
| JSON live check | `https://milk-ledger.onrender.com/health/live` |
| Dashboard login | `https://milk-ledger.onrender.com/login` |
| WhatsApp webhook base | `https://milk-ledger.onrender.com/webhooks/whatsapp` |

## Normal verification

```bash
curl -i https://milk-ledger.onrender.com/health
curl -s https://milk-ledger.onrender.com/health/live
```

Expected result:

- `/health` returns `200 OK` and plain text `OK`.
- `/health/live` returns JSON with `ok: true` when the app and dependent runtime checks are healthy.

## Render backend deployment

Render uses `render.yaml`:

```text
buildCommand: pip install -r backend/requirements.txt
startCommand: python backend/manage_db.py && gunicorn wsgi:app
healthCheckPath: /health
```

Required secret values are configured in Render, not committed to GitHub:

- `SECRET_KEY`
- `PASSWORD_RESET_KEY`
- `SUPABASE_URL`
- `SUPABASE_KEY`
- `SUPABASE_DB_URL`
- WhatsApp Cloud API credentials, when webhook features are enabled

## Vercel frontend deployment

The Vercel project root is `frontend/`.

Required Vercel environment variable:

```text
API_URL=https://milk-ledger.onrender.com
```

The frontend loads `/api/config.js`, which injects the configured backend URL into the browser at runtime.

## Supabase migration flow

1. Add SQL migration under `supabase/migrations/`.
2. Apply migration with Supabase CLI or allow the backend startup validation to apply SQL when configured with direct DB access.
3. Confirm schema cache reload and app health.

```bash
supabase db push --db-url "$SUPABASE_DB_URL"
python backend/manage_db.py
```

## Common incidents

### Backend does not start

Check Render logs for:

- Missing `SECRET_KEY` in production.
- Invalid `SUPABASE_DB_URL` format.
- Supabase connection timeout.
- Migration SQL failure.

### Frontend loads but buttons do not work

Check Vercel environment variable `API_URL`. The browser should fetch `/api/config.js` and receive:

```javascript
window.MILK_LEDGER_CONFIG = { API_URL: "https://milk-ledger.onrender.com" }
```

### Health check is degraded

Run:

```bash
curl -s https://milk-ledger.onrender.com/health/live
```

Then inspect the failing check in Render logs. The app is designed to continue in degraded mode when admin DB validation is temporarily unavailable, but production fixes should still be applied promptly.

### WhatsApp webhook verification fails

Confirm:

- Meta webhook callback URL points to `/webhooks/whatsapp`.
- `WHATSAPP_VERIFY_TOKEN` matches the Meta app configuration.
- `TRUSTED_HOSTS` includes the Render backend hostname.
- Render logs show incoming GET verification requests.

## Rollback approach

- Render: rollback to a previous deploy from the Render dashboard.
- Vercel: promote a previous deployment from the Vercel dashboard.
- Supabase: review migration history before applying corrective SQL; do not manually edit production tables without a recorded migration.

## Security and hygiene

- Do not commit `.env`, Supabase service-role keys, Meta tokens, or database URLs with passwords.
- Keep `SESSION_COOKIE_SECURE=true` and `TRUST_PROXY=true` in production.
- Keep `TRUSTED_HOSTS` restricted to the real Vercel and Render hostnames.
- Run CI tests before deploying changes to the backend.
