param(
    [string]$HostAddress = "127.0.0.1",
    [int]$Port = 8000,
    [switch]$SkipInfrastructure,
    [switch]$IncludeMinio
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$backendPath = Join-Path $projectRoot "backend"
$pythonPath = Join-Path $backendPath ".venv\Scripts\python.exe"

if (-not (Test-Path $pythonPath)) {
    throw "Python environment is missing. Run .\scripts\setup-backend-native.ps1 first."
}

Set-Location $projectRoot

if (-not (Test-Path (Join-Path $backendPath ".env.local"))) {
    throw "Missing backend/.env.local. Run .\scripts\init-dev-env.ps1 first."
}

if (-not $SkipInfrastructure) {
    docker compose up -d db redis
    if ($LASTEXITCODE -ne 0) {
        throw "Docker infrastructure failed to start. Check whether ports 5432 and 6379 are available."
    }
    if ($IncludeMinio) {
        docker compose up -d minio
        if ($LASTEXITCODE -ne 0) {
            throw "MinIO failed to start. Check whether ports 9000 and 9001 are available."
        }
    }
}

Set-Location $backendPath
& $pythonPath manage.py migrate --noinput
if ($LASTEXITCODE -ne 0) { throw "Django migrations failed." }
Write-Host "Launching Mobile Discovery backend..." -ForegroundColor Cyan
& $pythonPath manage.py runserver "${HostAddress}:${Port}"

