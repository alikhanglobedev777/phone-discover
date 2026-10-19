# Render deployment — Phone Discover

This project needs **three Render resources**: a PostgreSQL database, a Django Python web service,
and a React/Vite static site. The 48-hour price refresh needs an optional paid Render Cron Job.
Do not deploy the local `dev.py` launcher, local Docker Compose, or Windows scheduled task.

## 0. Before deploying

- Rotate the Gemini/Groq keys, PostgreSQL password, and Django secret previously exposed in logs/chat.
- Never commit `.env.local`, API keys, Postgres dumps, or passwords.
- Commit the code to GitHub/GitLab; Render deploys from your Git repository.
- For production, use paid Postgres: free Render Postgres expires after 30 days.
- This guide deploys a NEW database. Your existing Windows PostgreSQL data will not appear unless you import it.

## 1. Render PostgreSQL

Create **New → Postgres**. Choose a plan/region, save, and copy its **internal database URL**.
Keep Django in the same region as PostgreSQL.

## 2. Django API web service

Create **New → Web Service**, connect the repo, and enter:

| Setting | Value |
| --- | --- |
| Root Directory | `backend` |
| Language | Python |
| Build Command | `pip install -r requirements.txt && python manage.py collectstatic --noinput` |
| Start Command | `python manage.py migrate --noinput && gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --timeout 120` |
| Health Check Path | `/api/health/` |

Use the Render Environment panel to set **all** these variables (illustrative service names only):

```dotenv
PYTHON_VERSION=3.12.11
DATABASE_URL=<internal URL of your Render PostgreSQL>
DJANGO_SECRET_KEY=<new strong random secret, 32+ chars>
DJANGO_DEBUG=0
DJANGO_ALLOWED_HOSTS=your-api-name.onrender.com
DJANGO_TRUST_PROXY_HEADERS=1
DJANGO_SECURE_SSL_REDIRECT=1
CSRF_TRUSTED_ORIGINS=https://your-api-name.onrender.com,https://your-site-name.onrender.com
CORS_ALLOWED_ORIGINS=https://your-site-name.onrender.com
DJANGO_USE_REDIS_CACHE=0
RESEARCH_JOB_QUEUE_ENABLED=0
AI_PROVIDER=groq
GROQ_API_KEY=<private new Groq key>
GROQ_MODEL=openai/gpt-oss-20b
GROQ_WEB_MODEL=openai/gpt-oss-20b
WEB_SEARCH_PROVIDER=groq
GEMINI_WEB_RESEARCH_ENABLED=1
GEMINI_AUTO_RESEARCH_ENABLED=1
```

The two `GEMINI_...` toggles are the existing project's research feature switches,
not instructions to route research through Gemini. Adjust them only after checking
that the previously applied Groq research patch supports them.

Replace the hostnames with Render's **actual** assigned hostnames (no protocol in
`DJANGO_ALLOWED_HOSTS`, but `https://` for CORS/CSRF origins). Do not include quotes
around values in Render's environment input. Deploy the backend and visit
`https://your-api-name.onrender.com/api/health/`; expect `{"status":"ok"}`.

The migration command is placed in Start Command for compatibility with the free tier.
On a paid plan, a dedicated pre-deploy migration step is preferable.

## 3. React/Vite static site

Create **New → Static Site** from the SAME repository:

| Setting | Value |
| --- | --- |
| Root Directory | `frontend` |
| Build Command | `npm ci && npm run build` |
| Publish Directory | `dist` |
| Environment variable | `VITE_API_BASE_URL=https://your-api-name.onrender.com` |

The build-time `VITE_API_BASE_URL` is public and must contain **only** the API origin,
not an API key. For React Router browser paths, add a Rewrite: `/*` → `/index.html`.
Redeploy after changing `VITE_API_BASE_URL` or CORS settings.

## 4. First admin login and existing data

Visit `https://your-api-name.onrender.com/admin/`. An existing local admin account
is not included in the NEW Render database. On paid Render web services, use Shell:
`python manage.py createsuperuser`. Free web services **do not provide Shell**.
An alternative is to create a superuser from your own computer with Django using
the Render database **external** connection URL temporarily, over a restricted
connection, and then restore your local settings. Never expose admin credentials
or embed them in committed code.

If you want your local catalog, variants, verified research evidence and prices,
export/import PostgreSQL data separately via `pg_dump` and `pg_restore`. Do not
assume `migrate` will copy the existing records.

## 5. Price refresh every 2 calendar days (optional, paid)

Create **New → Cron Job**, root directory `backend`, Python runtime, same database
and Groq environment settings. Example:

- Build: `pip install -r requirements.txt`
- Schedule (UTC): `0 9 */2 * *`
- Command: `python manage.py refresh_phone_prices`

**Note:** `*/2` means alternate calendar days, **not** a strict 48-hour interval
across month boundaries. For exactly 48-hour spacing, schedule daily and make the
command check the last successful run timestamp before doing work.
Cron Jobs have a minimum monthly charge and are not part of the free service tier.
Check credentials, quotas, web source permissions, and price-review rules.

## 6. Security / release checklist

- `DJANGO_DEBUG=0`; unique private `DJANGO_SECRET_KEY`; explicit allowed hosts.
- Confirm HTTPS, CORS, CSRF, `/api/health/`, `/admin/`, and visible phone data.
- Test chatbot's missing-phone Groq lookup and confirm source evidence, not fabricated prices.
- Verify 48-hour refresh in Render cron run logs.
- All uploaded media need object storage; Render web service filesystem is ephemeral.
- Configure a shared Redis cache if using multiple Django workers/instances for throttling.
- Free web servers sleep and Free Postgres expires; use paid resources for real users.
