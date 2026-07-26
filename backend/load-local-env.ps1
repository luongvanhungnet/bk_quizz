$EnvFile = Join-Path $PSScriptRoot ".env.local"

if (-not (Test-Path $EnvFile)) {
    throw "Không tìm thấy file: $EnvFile"
}

Get-Content $EnvFile |
ForEach-Object {
    $Line = $_.Trim()

    if (
        -not $Line -or
        $Line.StartsWith("#") -or
        -not $Line.Contains("=")
    ) {
        return
    }

    $Name, $Value = $Line -split "=", 2

    $Name = $Name.Trim()
    $Value = $Value.Trim()

    if (
        $Value.Length -ge 2 -and
        (
            (
                $Value.StartsWith('"') -and
                $Value.EndsWith('"')
            ) -or
            (
                $Value.StartsWith("'") -and
                $Value.EndsWith("'")
            )
        )
    ) {
        $Value = $Value.Substring(
            1,
            $Value.Length - 2
        )
    }

    [Environment]::SetEnvironmentVariable(
        $Name,
        $Value,
        "Process"
    )
}

$Utf8JvmOptions = "-Dfile.encoding=UTF-8 -Dstdout.encoding=UTF-8 -Dstderr.encoding=UTF-8"
if (-not $env:JAVA_TOOL_OPTIONS) {
    $env:JAVA_TOOL_OPTIONS = $Utf8JvmOptions
} elseif (-not $env:JAVA_TOOL_OPTIONS.Contains("-Dstdout.encoding=")) {
    $env:JAVA_TOOL_OPTIONS = "$env:JAVA_TOOL_OPTIONS $Utf8JvmOptions"
}
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)

Write-Host "Đã nạp biến môi trường từ $EnvFile"
Write-Host "PORT=$env:PORT"
Write-Host "DATABASE_URL=$env:DATABASE_URL"
Write-Host "DATABASE_USERNAME=$env:DATABASE_USERNAME"
Write-Host "RAG_ENABLED=$env:RAG_ENABLED"
Write-Host "WORKER_ENABLED=$env:WORKER_ENABLED"

if ($env:JWT_ACCESS_SECRET) {
    Write-Host `
      "JWT_ACCESS_SECRET length=$($env:JWT_ACCESS_SECRET.Length)"
}

if ($env:DATABASE_PASSWORD) {
    Write-Host `
      "DATABASE_PASSWORD length=$($env:DATABASE_PASSWORD.Length)"
}
