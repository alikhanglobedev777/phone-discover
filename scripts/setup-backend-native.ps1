param(
    [switch]$SkipInfrastructure,
    [switch]$IncludeMinio
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$backendPath = Join-Path $projectRoot "backend"
$virtualEnvironmentPath = Join-Path $backendPath ".venv"
$pythonPath = Join-Path $virtualEnvironmentPath "Scripts\python.exe"
$environmentExamplePath = Join-Path $backendPath ".env.local.example"
$environmentPath = Join-Path $backendPath ".env.local"

function Find-PythonExecutable {
    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($launcher) {
        $resolved = & $launcher.Source -3.12 -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $resolved) {
            return (@($resolved)[-1]).Trim()
        }
    }

    $pythonRoot = Join-Path $env:LOCALAPPDATA "Programs\Python"
    if (Test-Path $pythonRoot) {
        $installedPython = Get-ChildItem $pythonRoot -Filter python.exe -Recurse -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -notmatch "\\Scripts\\" } |
            Sort-Object FullName -Descending |
            Select-Object -First 1
        if ($installedPython) {
            return $installedPython.FullName
        }
    }

    throw "Python 3.12 or newer was not found. Install it with: winget install -e --id Python.Python.3.12 --scope user"
}

Set-Location $projectRoot

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

if (-not (Test-Path $environmentPath)) {
    Copy-Item $environmentExamplePath $environmentPath
    Write-Host "Created backend/.env.local" -ForegroundColor Cyan
}

Write-Host "Installing backend dependencies..." -ForegroundColor Cyan
& $pythonPath -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed." }
& $pythonPath -m pip install -r (Join-Path $backendPath "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "Backend dependency installation failed." }

Write-Host "Applying database migrations..." -ForegroundColor Cyan
Set-Location $backendPath
& $pythonPath manage.py migrate
if ($LASTEXITCODE -ne 0) { throw "Django migrations failed." }

Write-Host "Native Django setup complete." -ForegroundColor Green
Write-Host "Start it with: .\scripts\run-backend-native.ps1"

