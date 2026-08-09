param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("api", "worker", "beat")]
    [string]$Service
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$EnvFile = Join-Path $Root ".env"
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Không tìm thấy Python virtual environment tại $Python"
}
if (-not (Test-Path -LiteralPath $EnvFile)) {
    throw "Không tìm thấy $EnvFile. Hãy sao chép .env.example thành .env."
}

$PreviousValues = @{}
$LoadedNames = [System.Collections.Generic.List[string]]::new()
foreach ($Line in Get-Content -LiteralPath $EnvFile -Encoding UTF8) {
    $Trimmed = $Line.Trim()
    if (-not $Trimmed -or $Trimmed.StartsWith("#")) { continue }
    if ($Trimmed -notmatch '^([A-Za-z_][A-Za-z0-9_]*)=(.*)$') { continue }
    $Name = $Matches[1]
    $Value = $Matches[2].Trim()
    if (($Value.StartsWith('"') -and $Value.EndsWith('"')) -or
        ($Value.StartsWith("'") -and $Value.EndsWith("'"))) {
        $Value = $Value.Substring(1, $Value.Length - 2)
    }
    $PreviousValues[$Name] = [Environment]::GetEnvironmentVariable($Name, "Process")
    [Environment]::SetEnvironmentVariable($Name, $Value, "Process")
    $LoadedNames.Add($Name)
}

function Assert-RedisAvailable {
    $RedisUrl = [Environment]::GetEnvironmentVariable("REDIS_URL", "Process")
    if (-not $RedisUrl) { $RedisUrl = "redis://127.0.0.1:6379/0" }
    $Uri = [Uri]$RedisUrl
    $Client = [System.Net.Sockets.TcpClient]::new()
    try {
        $Connect = $Client.BeginConnect($Uri.Host, $Uri.Port, $null, $null)
        if (-not $Connect.AsyncWaitHandle.WaitOne(1500) -or -not $Client.Connected) {
            throw "Redis chưa hoạt động tại $($Uri.Host):$($Uri.Port)."
        }
        $Client.EndConnect($Connect)
    }
    finally { $Client.Dispose() }
}

try {
    Set-Location -LiteralPath $Root
    Write-Host "Đã nạp cấu hình từ $EnvFile cho tiến trình $Service."
    Write-Host "RAG root: $Root"
    Write-Host "Python: $Python"
    switch ($Service) {
        "api" {
            & $Python -m uvicorn app.main:app --host 127.0.0.1 --port 8090 --workers 1
        }
        "worker" {
            Assert-RedisAvailable
            & $Python -m celery -A app.worker.celery_app:celery_app worker --pool=solo --concurrency=1 --loglevel=INFO
        }
        "beat" {
            Assert-RedisAvailable
            & $Python -m celery -A app.worker.celery_app:celery_app beat --loglevel=INFO
        }
    }
    exit $LASTEXITCODE
}
finally {
    foreach ($Name in $LoadedNames) {
        [Environment]::SetEnvironmentVariable($Name, $PreviousValues[$Name], "Process")
    }
}
