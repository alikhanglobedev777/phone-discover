# Read-only end-to-end verification for the Windows native developer setup.
# Does not print API keys, modify the database, call Gemini, or deploy services.
param(
    [switch]$Production,
    [switch]$RequireMarketData
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root "backend\.venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Python virtualenv missing. Run scripts/setup-backend-native.ps1 first."
}

function Assert-Success([string]$Step) {
    if ($LASTEXITCODE -ne 0) { throw "$Step failed (exit code $LASTEXITCODE). Stop before committing." }
}

Push-Location -LiteralPath (Join-Path $root "backend")
try {
    & $python manage.py check
    Assert-Success "Django system check"
    & $python manage.py makemigrations --check --dry-run
    Assert-Success "Migration file check"
    & $python manage.py test config catalog recommendations
    Assert-Success "Backend tests"

    $argsList = @("manage.py", "release_check", "--database")
    if ($Production) { $argsList += @("--production", "--cache") }
    if ($RequireMarketData) { $argsList += "--require-market-data" }
    & $python @argsList
    Assert-Success "Release preflight"
} finally { Pop-Location }

Push-Location -LiteralPath (Join-Path $root "frontend")
try {
    if (-not (Test-Path -LiteralPath "node_modules")) {
        throw "Node modules missing. Run npm ci from the frontend directory."
    }
    npm run lint
    Assert-Success "Frontend TypeScript check"
    npm run test:ui
    Assert-Success "Frontend tests"
    npm run build
    Assert-Success "Frontend build"
} finally { Pop-Location }

Push-Location -LiteralPath $root
try {
    git -c core.whitespace=cr-at-eol diff --check
    Assert-Success "Git whitespace check"
    Write-Host "PASS: release verification completed. No deployment was performed." -ForegroundColor Green
} finally { Pop-Location }
