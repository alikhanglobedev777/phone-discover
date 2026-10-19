$ErrorActionPreference = 'Stop'
Unregister-ScheduledTask -TaskName 'PhoneDiscoverPriceRefresh' -Confirm:$false
Write-Host 'Price refresh schedule removed.' -ForegroundColor Green
