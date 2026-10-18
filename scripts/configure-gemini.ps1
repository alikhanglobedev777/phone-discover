param(
    [string]$Model = "gemini-3.8-flash",
    [switch]$TestConnection
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$backendPath = Join-Path $projectRoot "backend"
$environmentPath = Join-Path $backendPath ".env.local"
$pythonPath = Join-Path $backendPath ".venv\Scripts\python.exe"

function Set-DotEnvValue {
    param(
        [string]$Path,
        [string]$Name,
        [string]$Value
    )

    $lines = [System.Collections.Generic.List[string]]::new()
    if (Test-Path $Path) {
        foreach ($line in [System.IO.File]::ReadAllLines($Path)) {
            $lines.Add($line)
        }
    }

    $replacement = "$Name=$Value"
    $updated = $false
    for ($index = 0; $index -lt $lines.Count; $index++) {
        if ($lines[$index] -match "^\s*$([Regex]::Escape($Name))\s*=") {
            $lines[$index] = $replacement
            $updated = $true
            break
        }
    }
    if (-not $updated) {
        $lines.Add($replacement)
    }

    $utf8WithoutBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllLines($Path, [string[]]$lines, $utf8WithoutBom)
}

if (-not (Test-Path $environmentPath)) {
    & (Join-Path $PSScriptRoot "init-dev-env.ps1")
    if (-not $?) { throw "Development environment initialization failed." }
}

Write-Host "Configure Gemini for Mobile Discovery" -ForegroundColor Cyan
Write-Host "The key is entered securely and will not be displayed." -ForegroundColor DarkGray
$secureKey = Read-Host "Paste your Gemini API key" -AsSecureString
$keyPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
try {
    $apiKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($keyPointer)
}
finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($keyPointer)
}

if ([string]::IsNullOrWhiteSpace($apiKey)) {
    throw "Gemini API key cannot be blank."
}

Set-DotEnvValue -Path $environmentPath -Name "AI_PROVIDER" -Value "gemini"
Set-DotEnvValue -Path $environmentPath -Name "GEMINI_API_KEY" -Value $apiKey.Trim()
Set-DotEnvValue -Path $environmentPath -Name "GEMINI_CHAT_MODEL" -Value $Model
$apiKey = $null

Write-Host "Gemini configuration saved securely in backend/.env.local" -ForegroundColor Green

if (Test-Path $pythonPath) {
    Set-Location $backendPath
    $arguments = @("manage.py", "check_ai_provider")
    if ($TestConnection) {
        $arguments += "--live"
    }
    & $pythonPath @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Gemini configuration check failed."
    }
}
else {
    Write-Host "Run .\scripts\setup-backend-native.ps1 before testing the connection." -ForegroundColor Yellow
}

Set-Location $projectRoot
Write-Host "Restart the backend with: .\scripts\run-backend-native.ps1 -SkipInfrastructure" -ForegroundColor Cyan
