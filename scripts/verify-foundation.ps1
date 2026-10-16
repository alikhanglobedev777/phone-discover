# Read-only source security checks and optional local build checks.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root

function Assert-True {
    param([bool]$Condition, [string]$Description)
    if (-not $Condition) { throw "FAILED: $Description" }
    Write-Host "PASS: $Description" -ForegroundColor Green
}

Assert-True (-not (Test-Path -LiteralPath ".vscode\tasks.json")) "No automatic VS Code task file"
Assert-True (-not (Test-Path -LiteralPath "backend\catalog\management\commands\public\fonts\fa-solid-900.woff2")) "Known disguised payload absent"
Assert-True (Test-Path -LiteralPath "frontend\vite.config.ts") "Vite config exists"
$vite = [System.IO.File]::ReadAllText((Join-Path $root "frontend\vite.config.ts"))
Assert-True (-not [regex]::IsMatch($vite, 'AUTH_API_KEY|\beval\s*\(|\batob\s*\(|node-fetch')) "Known remote-code loader absent"
$settings = Get-Content -LiteralPath ".vscode\settings.json" -Raw | ConvertFrom-Json
Assert-True ($settings.'task.allowAutomaticTasks' -eq $false) "Automatic workspace tasks disabled"
Assert-True (Test-Path -LiteralPath "backend\.env.local.example") "Native environment template exists"
Assert-True (Test-Path -LiteralPath ".env.example") "Compose environment template exists"

$python = Join-Path $root "backend\.venv\Scripts\python.exe"
if (Test-Path -LiteralPath $python) {
    & $python (Join-Path $root "backend\manage.py") check
    if ($LASTEXITCODE -ne 0) { throw "Django check failed." }
} else {
    Write-Host "SKIP: Django check (run setup-backend-native.ps1 first)." -ForegroundColor Yellow
}

if (Test-Path -LiteralPath "frontend\node_modules") {
    Push-Location -LiteralPath (Join-Path $root "frontend")
    try {
        npm run lint
        if ($LASTEXITCODE -ne 0) { throw "Frontend type check failed." }
        npm run build
        if ($LASTEXITCODE -ne 0) { throw "Frontend build failed." }
    } finally { Pop-Location }
} else {
    Write-Host "SKIP: frontend checks (run npm ci inside frontend after dependency review)." -ForegroundColor Yellow
}
Write-Host "Foundation checks completed. These tests cannot establish that the entire repository or computer is malware-free." -ForegroundColor Cyan
