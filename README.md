# Mobile Discovery

A phone catalog and explainable recommendation assistant built with React, Django, PostgreSQL, Redis, and MinIO.

Current capabilities include structured phone specifications, market offers,
advanced filtering, a shareable three-phone comparison, and a catalog-grounded
buying assistant with optional OpenAI explanations.

## Local setup

```powershell
Copy-Item .env.example .env
docker compose up --build
```

Frontend: http://localhost:5173
Backend: http://localhost:8000
Admin: http://localhost:8000/admin/

The backend container runs migrations automatically. Create an admin user in another terminal:

```powershell
docker compose exec backend python manage.py createsuperuser
```

Seed local demo data:

```powershell
docker compose exec backend python manage.py seed_demo
```

Import a CSV from the host machine:

```powershell
docker compose cp .\catalog.csv backend:/tmp/catalog.csv
docker compose exec backend python manage.py import_catalog /tmp/catalog.csv
```

Required CSV columns: `brand,device,variant,ram_gb,storage_gb`. Optional columns include `summary,operating_system,battery_mah,display_refresh_hz,chipset,camera_score,gaming_score,battery_score,country_code,currency,price,seller_name,product_url,is_affiliate`.

## Patch order

Apply the supplied patches in numeric order with `git apply`.

See `docs/native-development.md`, `docs/catalog-admin.md`, and
`docs/recommendation-assistant.md` for the current native Windows workflow.
