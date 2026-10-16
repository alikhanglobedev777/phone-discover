param(
    [switch]$SkipInfrastructure,
    [switch]$IncludeMinio
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$backendPath = Join-Path $projectRoot "backend"
$virtualEnvironmentPath = Join-Path $backendPath ".venv"
$pythonPath = Join-Path $virtualEnvironmentPath "Scripts\python.exe"

function Find-PythonExecutable {
    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($launcher) {
        foreach ($selector in @("-3.13", "-3.12", "-3")) {
            $resolved = & $launcher.Source $selector -c "import sys; print(sys.executable if sys.version_info >= (3,12) else '')" 2>$null
            if ($LASTEXITCODE -eq 0 -and $resolved) {
                return (@($resolved)[-1]).Trim()
            }
        }
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        $resolved = & $python.Source -c "import sys; print(sys.executable if sys.version_info >= (3,12) else '')" 2>$null
        if ($LASTEXITCODE -eq 0 -and $resolved) {
            return (@($resolved)[-1]).Trim()
        }
    }

    throw "Python 3.12 or newer was not found. Install it from python.org or via winget."
}

Set-Location $projectRoot

# Create both development env files before Compose reads its root .env.
& (Join-Path $PSScriptRoot "init-dev-env.ps1")
if (-not $?) { throw "Development environment initialization failed." }

if (-not $SkipInfrastructure) {
    Write-Host "Starting PostgreSQL and Redis..." -ForegroundColor Cyan
    docker compose stop backend frontend | Out-Null
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

if (-not (Test-Path $pythonPath)) {
    Write-Host "Creating Python virtual environment..." -ForegroundColor Cyan
    $systemPython = Find-PythonExecutable
    Write-Host "Using Python: $systemPython" -ForegroundColor DarkGray
    & $systemPython -m venv $virtualEnvironmentPath
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $pythonPath)) {
        throw "Python virtual environment creation failed."
    }
}

Write-Host "Installing backend dependencies..." -ForegroundColor Cyan
& $pythonPath -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed." }
& $pythonPath -m pip install -r (Join-Path $backendPath "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "Backend dependency installation failed." }

Write-Host "Validating Django configuration..." -ForegroundColor Cyan
Set-Location $backendPath
& $pythonPath manage.py check
if ($LASTEXITCODE -ne 0) { throw "Django system checks failed." }

Write-Host "Applying database migrations..." -ForegroundColor Cyan
& $pythonPath manage.py migrate
if ($LASTEXITCODE -ne 0) { throw "Django migrations failed." }

Write-Host "Native Django setup complete." -ForegroundColor Green
Write-Host "Start it with: .\scripts\run-backend-native.ps1"

