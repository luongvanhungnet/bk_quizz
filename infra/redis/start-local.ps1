$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$PidFile = Join-Path $Root 'tmp/redis-wsl-keeper.pid'
New-Item -ItemType Directory -Path (Split-Path -Parent $PidFile) -Force | Out-Null

# Keep WSL running while Windows clients use Redis; systemd services alone
# do not reliably keep a WSL distribution alive.
$Keeper = $null
if (Test-Path -LiteralPath $PidFile) {
    $KeeperId = (Get-Content -LiteralPath $PidFile -Raw).Trim()
    if ($KeeperId -match '^\d+$') {
        $Keeper = Get-CimInstance Win32_Process -Filter "ProcessId = $KeeperId" |
            Where-Object { $_.Name -eq 'wsl.exe' -and $_.CommandLine -match 'Ubuntu.*sleep infinity' }
    }
}
if (-not $Keeper) {
    $KeeperProcess = Start-Process wsl.exe -ArgumentList '-d Ubuntu -u root --exec sleep infinity' -WindowStyle Hidden -PassThru
    Set-Content -LiteralPath $PidFile -Value $KeeperProcess.Id
}

& wsl.exe -d Ubuntu -u root -- systemctl start redis-server
if ($LASTEXITCODE -ne 0) { throw 'Redis service could not start.' }
& wsl.exe -d Ubuntu -u root -- redis-cli ping
if ($LASTEXITCODE -ne 0) { throw 'Redis PING failed.' }
Write-Host 'Redis local: redis://127.0.0.1:6379/0'
