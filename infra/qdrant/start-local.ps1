$ErrorActionPreference = 'Stop'
# Reuse the Redis launcher to keep the shared Ubuntu WSL runtime alive.
& (Join-Path $PSScriptRoot '../redis/start-local.ps1')
& wsl.exe -d Ubuntu -u root -- systemctl start qdrant
if ($LASTEXITCODE -ne 0) { throw 'Qdrant service could not start.' }
$Ready = $false
for ($Attempt = 0; $Attempt -lt 15; $Attempt++) {
    try {
        Invoke-RestMethod 'http://127.0.0.1:6333/readyz' -TimeoutSec 2 | Out-Null
        $Ready = $true
        break
    } catch { Start-Sleep -Seconds 1 }
}
if (-not $Ready) { throw 'Qdrant readiness check failed.' }
Write-Host 'Qdrant local: http://127.0.0.1:6333'
