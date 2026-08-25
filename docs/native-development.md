# Native development on Windows

Django and React run natively. PostgreSQL and Redis run through Docker Compose.

## First setup

From the project root in PowerShell:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\setup-backend-native.ps1
```

The setup script discovers the real Python installation, creates `backend/.venv`,
copies `backend/.env.local.example` to `backend/.env.local`, installs dependencies,
starts PostgreSQL and Redis, and applies migrations.

If another local PostgreSQL service owns port 5432, stop it before running the
script or change the host port in `docker-compose.yml` and `backend/.env.local`.

## Start Django

```powershell
.\scripts\run-backend-native.ps1
```

Add `-IncludeMinio` when object storage is needed:

```powershell
.\scripts\run-backend-native.ps1 -IncludeMinio
```

## Start React

In a second PowerShell window:

```powershell
cd frontend
npm install
npm run dev
```

Django: http://127.0.0.1:8000

React: http://localhost:5173

When Django has successfully bound to its port, the terminal prints a colored
Mobile Discovery banner with the server, admin, and API URLs.
