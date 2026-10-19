# Launch Django from the project root or backend folder using `npm run dev`.
# The first run uses the repository's existing native-Windows setup scripts.
param([switch]$SkipInfrastructure)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$backendPath = Join-Path $projectRoot "backend"
$pythonPath = Join-Path $backendPath ".venv\Scripts\python.exe"
$environmentPath = Join-Path $backendPath ".env.local"
$requirementsPath = Join-Path $backendPath "requirements.txt"
$requirementsStamp = Join-Path $backendPath ".venv\requirements.sha256"
$setupScript = Join-Path $PSScriptRoot "setup-backend-native.ps1"
$runScript = Join-Path $PSScriptRoot "run-backend-native.ps1"

try {
    $requirementsHash = (Get-FileHash -LiteralPath $requirementsPath -Algorithm SHA256).Hash
    $needsSetup = (-not (Test-Path -LiteralPath $pythonPath)) -or
                  (-not (Test-Path -LiteralPath $environmentPath)) -or
                  (-not (Test-Path -LiteralPath $requirementsStamp))

    if (-not $needsSetup) {
        $previousHash = (Get-Content -LiteralPath $requirementsStamp -Raw).Trim()
        $needsSetup = $previousHash -ne $requirementsHash
    }

    if (-not $needsSetup) {
        & $pythonPath -c "import django, rest_framework, corsheaders, django_filters, psycopg, dj_database_url, dotenv"
        $needsSetup = $LASTEXITCODE -ne 0
    }

    if ($needsSetup) {
        Write-Host "Preparing Django (first launch or dependencies changed)..." -ForegroundColor Cyan
        & $setupScript -SkipInfrastructure:$SkipInfrastructure
        if ($LASTEXITCODE -ne 0) {
            throw "Backend setup failed. See the error above."
        }
        # Stamp only after successful installation, validation and migrations.
        Set-Content -LiteralPath $requirementsStamp -Value $requirementsHash -Encoding ASCII
    }

    Write-Host "Starting Django on http://127.0.0.1:8000/" -ForegroundColor Green
    & $runScript -SkipInfrastructure:$SkipInfrastructure
    if ($LASTEXITCODE -ne 0) {
        throw "Django stopped with an error (exit code $LASTEXITCODE)."
    }
}
catch {
    Write-Host "Backend startup failed: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Normal mode needs Docker Desktop for PostgreSQL. If your PostgreSQL is already running separately, use: npm run dev:no-docker" -ForegroundColor Yellow
    exit 1
}
