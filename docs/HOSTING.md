# Hosting seo-api (FP-2)

> **Full project:** SEO-Agent is one service in `AI-AGENT-Projects`.  
> Prefer the **parent** stack: [`../DEPLOY.md`](../../DEPLOY.md) and root `docker-compose.yml`  
> (`seo-api` client + optional Hermes profile).

Put the FastAPI `seo-api` on **HTTPS** so clients (and you) stop depending on a laptop process.

## What “hosted” means

| Need | How |
|------|-----|
| Always-on HTTPS URL | Railway / Render / Fly / any Docker VPS |
| Secrets | Platform env vars (never commit `.env`) |
| Durable storage | Volume for SQLite **or** `SEO_DATABASE_URL` Postgres |
| SPA crawls (Actoro) | Image includes Playwright Chromium |
| PDF | Image includes `seo-agent[pdf]` |
| API lock | Set `SEO_API_KEY` in production |
| Google Connect | Set `GSC_REDIRECT_URI=https://YOUR_DOMAIN/auth/callback` + add that URI in Google Cloud |

After Host is live → **FP-3** (Publish OAuth consent) → thin client / Stripe.

## Quick local prod smoke (Docker)

```bash
cd SEO-Agent
# Ensure .env has real keys; set at least:
#   SEO_API_KEY=<long-random>
#   SEO_PLAYWRIGHT_ENABLED=true
docker compose up --build
curl -sS http://127.0.0.1:8000/health
open "http://127.0.0.1:8000/dashboard/ui?url=https://actoro.app/&gsc_account_id=demo"
```

## Required production env

Copy from `.env.example`, then set:

```bash
SEO_API_KEY=...                 # required when exposed
PORT=8000                       # platforms often inject PORT
SEO_STORAGE_PATH=/data/audits.db
# or:
# SEO_DATABASE_URL=postgresql://...

SEO_PLAYWRIGHT_ENABLED=true

GSC_CLIENT_ID=...
GSC_CLIENT_SECRET=...
# or mount secrets/google-oauth-client.json
GSC_REDIRECT_URI=https://YOUR_DOMAIN/auth/callback
GSC_OAUTH_PUBLISHING_STATUS=testing   # production after Cloud Publish
GSC_PRIVACY_POLICY_URL=https://YOUR_DOMAIN/legal/privacy
GSC_HOMEPAGE_URL=https://YOUR_DOMAIN/

GOOGLE_PAGESPEED_API_KEY=...
KEYWORD_API_PROVIDER=dataforseo
KEYWORD_API_LOGIN=...
KEYWORD_API_PASSWORD=...
OPENAI_API_KEY=...              # only if optimize advice needed
```

## Recommended: Railway (Docker)

1. Push this repo (or connect GitHub).  
2. New Project → Deploy from Dockerfile.  
3. Add a **Volume** mounted at `/data`.  
4. Paste production env vars (above).  
5. Generate domain → set `GSC_REDIRECT_URI=https://<railway-domain>/auth/callback`.  
6. In Google Cloud OAuth client, add the same redirect URI.  
7. Smoke: `GET https://<domain>/health` and open `/dashboard/ui?...`.

## Render

1. New **Web Service** → Docker.  
2. Persistent disk at `/data` (or use Render Postgres + `SEO_DATABASE_URL`).  
3. Same env as above; Render sets `PORT`.

## Fly.io

```bash
fly launch --dockerfile Dockerfile
fly volumes create seo_data --size 3
# attach volume at /data in fly.toml
fly secrets set SEO_API_KEY=... GSC_CLIENT_ID=... # etc
fly deploy
```

## VPS (any Docker host)

```bash
docker build -t seo-api .
docker run -d --name seo-api -p 8000:8000 \
  --env-file .env \
  -v seo_data:/data \
  -v "$PWD/secrets:/app/secrets:ro" \
  seo-api
# Put Caddy/nginx TLS in front → https://seo.yourdomain.com
```

## Owner checklist after first deploy

- [ ] `/health` returns `ok` and `api_auth_required: true`  
- [ ] Dashboard loads over HTTPS  
- [ ] Google OAuth redirect URI matches Cloud Console  
- [ ] Run one saved Actoro (or client) audit + PDF/share  
- [ ] Then validate **FP-3 OAuth Publish** if external clients must Connect Google  

## Out of scope for FP-2

Stripe, multi-tenant IAM, Slack alerts, Playwright *form* login — later Fast path / Future slices.
