# Generate private development configuration without displaying secrets.
# Never overwrites an existing .env or backend/.env.local.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$rootEnv = Join-Path $root ".env"
$nativeEnv = Join-Path $root "backend\.env.local"

function New-RandomHex {
    param([int]$Length = 32)
    $bytes = New-Object byte[] $Length
    $random = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $random.GetBytes($bytes) } finally { $random.Dispose() }
    return [BitConverter]::ToString($bytes).Replace("-", "").ToLowerInvariant()
}

function Get-EnvValue {
    param([string]$Contents, [string]$Name)
    $match = [regex]::Match($Contents, "(?m)^$([regex]::Escape($Name))=(.*)$")
    if (-not $match.Success) { throw "Missing required variable $Name in development environment." }
    return $match.Groups[1].Value.Trim()
}

function Set-EnvValue {
    param([string]$Contents, [string]$Name, [string]$Value)
    $pattern = "(?m)^$([regex]::Escape($Name))=.*$"
    if (-not [regex]::IsMatch($Contents, $pattern)) { throw "Missing template variable: $Name" }
    return [regex]::Replace($Contents, $pattern, "$Name=$Value")
}

function Write-PrivateEnv {
    param([string]$Path, [string]$Contents)
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    # CreateNew prevents accidental replacement even if another process created it.
    $stream = [System.IO.File]::Open($Path, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write)
    try {
        $bytes = $utf8.GetBytes($Contents)
        $stream.Write($bytes, 0, $bytes.Length)
    } finally { $stream.Dispose() }
}

if (-not (Test-Path -LiteralPath $rootEnv)) {
    $contents = [System.IO.File]::ReadAllText((Join-Path $root ".env.example"))
    $contents = Set-EnvValue $contents "DJANGO_SECRET_KEY" (New-RandomHex)
    $contents = Set-EnvValue $contents "POSTGRES_PASSWORD" (New-RandomHex 20)
    Write-PrivateEnv $rootEnv $contents
    Write-Host "Generated private root .env for Docker Compose." -ForegroundColor Green
} else {
    Write-Host "Keeping existing root .env unchanged." -ForegroundColor Cyan
}

$rootContents = [System.IO.File]::ReadAllText($rootEnv)
if ($rootContents -match '(?m)^AUTH_API_KEY\s*=') {
    throw "Unexpected AUTH_API_KEY in .env. Investigate this file before continuing."
}
$secret = Get-EnvValue $rootContents "DJANGO_SECRET_KEY"
$password = Get-EnvValue $rootContents "POSTGRES_PASSWORD"
if ($secret.Length -lt 32 -or [string]::IsNullOrWhiteSpace($password)) {
    throw "Development .env lacks a usable secret or database password; repair it manually."
}

if (-not (Test-Path -LiteralPath $nativeEnv)) {
    $contents = [System.IO.File]::ReadAllText((Join-Path $root "backend\.env.local.example"))
    foreach ($name in @("DJANGO_SECRET_KEY", "POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD")) {
        $contents = Set-EnvValue $contents $name (Get-EnvValue $rootContents $name)
    }
    Write-PrivateEnv $nativeEnv $contents
    Write-Host "Generated private backend/.env.local for native Django." -ForegroundColor Green
} else {
    Write-Host "Keeping existing backend/.env.local unchanged; confirm its DB credentials match .env." -ForegroundColor Yellow
}
Write-Host "Never commit .env or backend/.env.local. Gemini key is not required for Patch 01." -ForegroundColor Cyan
