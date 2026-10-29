param(
    [ValidateSet('Combined', 'Api', 'Worker')]
    [string]$Mode = 'Combined',
    [ValidateRange(0, 65535)]
    [int]$Port = 0
)

$ErrorActionPreference = 'Stop'
Push-Location -LiteralPath $PSScriptRoot
try {
    . (Join-Path $PSScriptRoot 'load-local-env.ps1')
    $env:WORKER_ENABLED = if ($Mode -eq 'Api') { 'false' } else { 'true' }
    if ($Port -gt 0) {
        $env:PORT = "$Port"
    } elseif ($Mode -eq 'Worker') {
        $env:PORT = '8081'
    } elseif (-not $env:PORT) {
        $env:PORT = '8080'
    }
    # All modes share the same working directory and default storage paths.
    Write-Host "Starting Spring mode=$Mode port=$env:PORT worker=$env:WORKER_ENABLED"
    & (Join-Path $PSScriptRoot 'mvnw.cmd') spring-boot:run
    $RunExitCode = $LASTEXITCODE
    if ($RunExitCode -ne 0) { throw "Spring exited with code $RunExitCode" }
} finally {
    Pop-Location
}
