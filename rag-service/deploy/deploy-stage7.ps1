[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = "Medium")]
param(
    [string]$ProjectId = "bkquiz-stg-235740",
    [string]$Region = "asia-southeast1",
    [string]$Service = "bkquiz-rag-api",
    [string]$CacheRedisSecret = "bkquiz-rag-cache-redis-url",
    [string]$CacheRedisSecretVersion = "1",
    [int]$MaxConnections = 10,
    [Parameter(Mandatory = $true)]
    [string]$Image,
    [switch]$ValidateOnly,
    [switch]$RemoveLegacyRedisBinding
)

$ErrorActionPreference = "Stop"

function Invoke-Gcloud {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    $previousErrorAction = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & gcloud @Arguments
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorAction
    }
    if ($exitCode -ne 0) {
        throw "gcloud command failed: gcloud $($Arguments -join ' ')"
    }
}

if (-not $ValidateOnly -and -not $PSCmdlet.ShouldProcess(
    "$ProjectId/$Region/$Service",
    "Deploy Stage 7 Upstash cache Redis"
)) {
    Write-Host "Would validate the image and Upstash secret, then deploy Stage 7."
    return
}

Invoke-Gcloud artifacts docker images describe $Image `
    --project=$ProjectId --format="value(image_summary.digest)"
$serviceJson = Invoke-Gcloud run services describe $Service `
    --project=$ProjectId --region=$Region --format=json | ConvertFrom-Json

$upstashUrl = Invoke-Gcloud secrets versions access $CacheRedisSecretVersion `
    --secret=$CacheRedisSecret --project=$ProjectId
$upstashUrl = ([string]$upstashUrl).Trim()
if (-not $upstashUrl.StartsWith("rediss://")) {
    throw "Upstash secret must contain a rediss:// connection URL."
}
try {
    $upstashUri = [Uri]$upstashUrl
}
catch {
    throw "Upstash secret does not contain a valid URI."
}
if (-not $upstashUri.Host.EndsWith(".upstash.io")) {
    throw "Upstash secret host must end with .upstash.io."
}

if ($ValidateOnly) {
    Write-Host "Image, Cloud Run service, and Upstash secret are valid."
    Write-Host "Upstash host: $($upstashUri.Host)"
    Write-Host "Secret value was validated but was not printed."
    return
}

$secretReference = "$CacheRedisSecret`:$CacheRedisSecretVersion"
$arguments = @(
    "run", "services", "update", $Service,
    "--project=$ProjectId",
    "--region=$Region",
    "--image=$Image",
    "--update-env-vars=CACHE_REDIS_PROVIDER=upstash,CACHE_REDIS_MAX_CONNECTIONS=$MaxConnections,INDEX_LOCK_MODE=redis",
    "--update-secrets=CACHE_REDIS_URL=$secretReference"
)

$environment = @($serviceJson.spec.template.spec.containers[0].env)
$removeEnvironmentNames = @()
$removeSecretNames = @()
$currentCacheBinding = @($environment | Where-Object name -eq "CACHE_REDIS_URL") | Select-Object -Last 1
if ($null -ne $currentCacheBinding -and -not $currentCacheBinding.valueFrom) {
    $removeEnvironmentNames += "CACHE_REDIS_URL"
}

if ($RemoveLegacyRedisBinding) {
    $legacyBinding = @($environment | Where-Object name -eq "REDIS_URL") | Select-Object -Last 1
    if ($null -ne $legacyBinding) {
        if ($legacyBinding.valueFrom) {
            $removeSecretNames += "REDIS_URL"
        }
        else {
            $removeEnvironmentNames += "REDIS_URL"
        }
    }
}

if ($removeEnvironmentNames.Count -gt 0) {
    $arguments += "--remove-env-vars=$($removeEnvironmentNames -join ',')"
}
if ($removeSecretNames.Count -gt 0) {
    $arguments += "--remove-secrets=$($removeSecretNames -join ',')"
}

Invoke-Gcloud @arguments

$updatedService = Invoke-Gcloud run services describe $Service `
    --project=$ProjectId --region=$Region --format=json | ConvertFrom-Json
$configured = @($updatedService.spec.template.spec.containers[0].env)
$cacheBinding = @($configured | Where-Object name -eq "CACHE_REDIS_URL") | Select-Object -Last 1
if ($null -eq $cacheBinding -or -not $cacheBinding.valueFrom) {
    throw "CACHE_REDIS_URL was not configured as a Secret Manager reference."
}

Write-Host "Stage 7 deployment completed."
Write-Host "Revision: $($updatedService.status.latestCreatedRevisionName)"
Write-Host "URL: $($updatedService.status.url)"
Write-Host "CACHE_REDIS_URL is stored as a secret reference."
if (-not $RemoveLegacyRedisBinding) {
    Write-Host "Legacy REDIS_URL was preserved for rollback."
}
